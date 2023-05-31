#!/usr/bin/env python3

import logging
import argparse
import os
import platform
import time
import multiprocessing

from diffusers import StableDiffusionPipeline
import torch
from dingtalk_stream import AckMessage
import dingtalk_stream
import messenger


def define_options():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--client_id', dest='client_id', required=True,
        help='app_key or suite_key from https://open-dev.digntalk.com'
    )
    parser.add_argument(
        '--client_secret', dest='client_secret', required=True,
        help='app_secret or suite_secret from https://open-dev.digntalk.com'
    )
    parser.add_argument(
        '--device', dest='device', required=False,
        help='device for pytorch, e.g. mps, cuda, etc.'
    )
    parser.add_argument(
        '--message_type', dest='message_type', default='card', required=False,
        help='device for pytorch, e.g. markdown, card, etc.'
    )
    parser.add_argument(
        '--subprocess', dest='subprocess', default=None, required=False, action='store_true',
        help='run stable diffusion in subprocess'
    )
    options = parser.parse_args()
    is_darwin = platform.system().lower() == 'darwin'
    is_google_colab = 'COLAB_RELEASE_TAG' in os.environ
    if options.device is None:
        if is_darwin:
            options.device = 'mps'
        if is_google_colab:
            options.device = 'cuda'
    if options.subprocess is None:
        if is_darwin:
            options.subprocess = True
        if is_google_colab:
            options.subprocess = False
    return options


def setup_logger():
    logger = logging.getLogger()
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter('%(asctime)s %(name)-8s %(levelname)-8s %(message)s [%(filename)s:%(lineno)d]'))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger


class ProgressBar(object):
    def __init__(self,
                 num_inference_steps: int,
                 image_count: int,
                 messenger: messenger.Messenger,
                 begin_time: float,
                 incoming_message: dingtalk_stream.ChatbotMessage):
        self.num_inference_steps: int = num_inference_steps
        self.image_count = image_count
        self.messenger: messenger.Messenger = messenger
        self.begin_time = begin_time
        self.incoming_message: dingtalk_stream.ChatbotMessage = incoming_message

    def callback(self, step: int, timestep, latents):
        if self.num_inference_steps <= 0 or step > self.num_inference_steps:
            return
        if step > 0:
            step -= 1
        elapse_seconds = time.time() - self.begin_time
        progress = '%d%%' % int(step*100 / self.num_inference_steps)
        is_new = False  # update cards instead of creating them
        self.messenger.reply_progress(is_new, progress, self.image_count, elapse_seconds, self.incoming_message)


class StableDiffusionBot(dingtalk_stream.ChatbotHandler):
    def __init__(self, options, logger: logging.Logger = None):
        super(StableDiffusionBot, self).__init__()
        if logger:
            self.logger = logger
        self._is_darwin = platform.system().lower() == 'darwin'
        self._is_google_colab = 'COLAB_RELEASE_TAG' in os.environ
        self._options = options
        self._pipe = None
        if not self._options.subprocess:
            self._pipe = self.create_pipe()
        self._enable_four_images = False
        self._task_queue = multiprocessing.Queue(maxsize=128)
        self._messenger: messenger.Messenger = None

    def pre_start(self):
        if self._options.subprocess:
            self.start_sd_process()
        else:
            self._messenger = messenger.Messenger(self.logger, self.dingtalk_client)

    def start_sd_process(self):
        from multiprocessing import Process
        p = Process(target=self.do_sd_process, daemon=True)
        p.start()
        self.logger.info('worker started, process=%s', p)

    def do_sd_process(self):
        self.logger = setup_logger()
        self._messenger = messenger.Messenger(self.logger, self.dingtalk_client)

        self.logger.info('do sd process ...')
        self._pipe = self.create_pipe()

        while True:
            incoming_message = self._task_queue.get()
            self.process_incoming_message(incoming_message)

    def create_pipe(self):
        torch_dtype = None if self._is_darwin else torch.float16
        pipe = StableDiffusionPipeline.from_pretrained("runwayml/stable-diffusion-v1-5", torch_dtype=torch_dtype)
        pipe = pipe.to(self._options.device)
        if self._is_darwin:
            # Recommended if your computer has < 64 GB of RAM
            pipe.enable_attention_slicing()
        return pipe

    def process_incoming_message(self, incoming_message):
        self.logger.info('get task, incoming_message=%s', incoming_message)
        try:
            begin_time = time.time()
            images = self.txt2img(self._pipe, begin_time, incoming_message)
            elapse_seconds = time.time() - begin_time
        except Exception as e:
            self.logger.error('do sd process failed, error=%s', e)
            return

        complete_task = {
            'images': images,
            'incoming_message': incoming_message,
            'elapse_seconds': elapse_seconds,
        }
        self.process_complete(complete_task)

    def txt2img(self, pipe, begin_time, incoming_message):
        image_count = 1
        if self._enable_four_images:
            image_count = 4
        is_new = True  # create card
        self._messenger.reply_progress(is_new, '0%', image_count, time.time() - begin_time, incoming_message)
        prompt = incoming_message.text.content.strip()
        num_inference_steps = 50 # default value
        progress = ProgressBar(num_inference_steps, image_count, self._messenger, begin_time, incoming_message)
        images = pipe(prompt,
                      num_inference_steps=num_inference_steps,
                      callback=progress.callback,
                      num_images_per_prompt=image_count).images
        if len(images) < image_count:
            self.logger.error('txt2img_four failed, not enough images, images.size=%d', len(images))
            return
        return images

    async def process(self, callback: dingtalk_stream.CallbackMessage):
        incoming_message = dingtalk_stream.ChatbotMessage.from_dict(callback.data)
        self.logger.info('received incoming message, message=%s', incoming_message)
        if self._options.subprocess:
            self._task_queue.put(incoming_message)
        else:
            self.process_incoming_message(incoming_message)
        return AckMessage.STATUS_OK, 'OK'

    def process_complete(self, complete_task):
        if not complete_task:
            return
        images = complete_task['images']
        elapse_seconds = complete_task['elapse_seconds']
        incoming_message = complete_task['incoming_message']
        self._messenger.reply(self._options.message_type, images, elapse_seconds, incoming_message)


def main():
    logger = setup_logger()
    options = define_options()

    credential = dingtalk_stream.Credential(options.client_id, options.client_secret)
    client = dingtalk_stream.DingTalkStreamClient(credential, logger=logger)

    client.register_callback_hanlder(dingtalk_stream.chatbot.ChatbotMessage.TOPIC,
                                     StableDiffusionBot(options, logger=logger))
    client.start_forever()


if __name__ == '__main__':
    main()
