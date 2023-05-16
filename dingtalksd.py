#!/usr/bin/env python3

import logging
import argparse
import io
import time
import multiprocessing
from PIL import Image

from diffusers import StableDiffusionPipeline
from dingtalk_stream import AckMessage
import dingtalk_stream


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
    options = parser.parse_args()
    return options


def setup_logger():
    logger = logging.getLogger()
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter('%(asctime)s %(name)-8s %(levelname)-8s %(message)s [%(filename)s:%(lineno)d]'))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger


class SDBotHandler(dingtalk_stream.ChatbotHandler):
    def __init__(self, logger: logging.Logger = None):
        super(SDBotHandler, self).__init__()
        if logger:
            self.logger = logger
        self._enable_four_images = True
        self._task_queue = multiprocessing.Queue(maxsize=32)

    def pre_start(self):
        self.start_sd_process()

    def start_sd_process(self):
        from multiprocessing import Process
        p = Process(target=self.do_sd_process, daemon=True)
        p.start()
        self.logger.info('worker started, process=%s', p)

    def do_sd_process(self):
        self.logger.info('do sd process ...')
        # pipe = StableDiffusionPipeline.from_pretrained("/Users/zealot/.cache/huggingface/hub/models--runwayml--stable-diffusion-v1-5/snapshots/39593d5650112b4cc580433f6b0435385882d819")
        pipe = StableDiffusionPipeline.from_pretrained("runwayml/stable-diffusion-v1-5")
        pipe = pipe.to("mps")
        # Recommended if your computer has < 64 GB of RAM
        pipe.enable_attention_slicing()

        while True:
            incoming_message = self._task_queue.get()
            self.logger.info('get task, incoming_message=%s', incoming_message)
            try:
                begin_time = time.time()
                image_content = self.txt2img(pipe, incoming_message)
                elapse_seconds = time.time() - begin_time
            except Exception as e:
                self.logger.error('do sd process failed, error=%s', e)
                continue

            complete_task = {
                'image': image_content,
                'incoming_message': incoming_message,
                'elapse_seconds': elapse_seconds,
            }
            self.process_complete(complete_task)
        return

    def txt2img(self, pipe, incoming_message):
        if self._enable_four_images:
            return self.txt2img_four(pipe, incoming_message)
        else:
            return self.txt2img_one(pipe, incoming_message)

    def txt2img_one(self, pipe, incoming_message):
        # First-time "warmup" pass (see explanation above)
        prompt = incoming_message.text.content.strip()
        _ = pipe(prompt, height=512, width=512, num_inference_steps=1)
        image = pipe(prompt, height=512, width=512).images[0]
        fp = io.BytesIO()
        image.save(fp, 'PNG')
        return fp.getvalue()

    def txt2img_four(self, pipe, incoming_message):
        # First-time "warmup" pass (see explanation above)
        prompt = incoming_message.text.content.strip()
        _ = pipe(prompt, height=512, width=512, num_inference_steps=1)
        images = pipe(prompt, height=512, width=512, num_images_per_prompt=4).images
        if len(images) < 4:
            self.logger.error('txt2img_four failed, not enough images, images.size=%d', len(images))
            return
        img_merge = Image.new('RGB', (1024, 1024))
        img_merge.paste(images[0], (0, 0))
        img_merge.paste(images[1], (512, 0))
        img_merge.paste(images[2], (0, 512))
        img_merge.paste(images[3], (512, 512))

        fp = io.BytesIO()
        img_merge.save(fp, 'PNG')
        return fp.getvalue()

    async def process(self, callback: dingtalk_stream.CallbackMessage):
        incoming_message = dingtalk_stream.ChatbotMessage.from_dict(callback.data)
        self.logger.info('received incoming message, message=%s', incoming_message)
        self._task_queue.put(incoming_message)
        return AckMessage.STATUS_OK, 'OK'

    def process_complete(self, complete_task):
        if not complete_task:
            return
        image = complete_task['image']
        elapse_seconds = complete_task['elapse_seconds']
        incoming_message = complete_task['incoming_message']
        response = self.reply_image(image, elapse_seconds, incoming_message)
        self.logger.info('reply image, response=%s', response)

    def reply_image(self, image_content, elapse_seconds, incoming_message):
        media_id = self.dingtalk_client.upload_to_dingtalk(image_content)
        self.logger.info('media_id=%s', media_id)
        title = 'Stable Diffusion txt2img'
        content = ('#### Prompts: %s\n\n'
                   '![image](%s)\n\n'
                   '> cost %ss\n'
                   '> \n'
                   '> Powered by Stable Diffusion\n'
                   '> \n'
                   '> via https://github.com/chzealot/dingtalk-stable-diffusion\n'
                   ) % (
                      incoming_message.text.content.strip(),
                      media_id,
                      round(elapse_seconds, 3)
                  )
        return self.reply_markdown(title, content, incoming_message)


def main():
    logger = setup_logger()
    options = define_options()

    credential = dingtalk_stream.Credential(options.client_id, options.client_secret)
    client = dingtalk_stream.DingTalkStreamClient(credential, logger=logger)

    client.register_callback_hanlder(dingtalk_stream.ChatbotMessage.TOPIC, SDBotHandler(logger=logger))
    client.start_forever()


if __name__ == '__main__':
    main()
