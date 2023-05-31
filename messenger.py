import io
import json
import hashlib

import dingtalk_stream
from PIL import Image
import requests


class Messenger(object):
    PROGRESS_MEDIA_ID = '@lALPDeC2-ctyLH_NAgDNAgA'

    def __init__(self, logger, dingtalk_client):
        self.logger = logger
        self.dingtalk_client = dingtalk_client

    def reply(self, message_type, images, elapse_seconds, incoming_message):
        if len(images) == 0:
            self.logger.error('empty image list')
            return
        if message_type == 'markdown':
            self.reply_markdown(images, elapse_seconds, incoming_message)
            return
        self.reply_card(images, elapse_seconds, incoming_message)

    def reply_progress(self, is_new: bool, progress: str, image_count: int, elapse_seconds: float,
                       incoming_message: dingtalk_stream.ChatbotMessage):
        self.logger.info('progress=%s, elapse=%.3fs, type=%s, cid=%s', progress, elapse_seconds,
                         incoming_message.conversation_type, incoming_message.conversation_id)
        images = [self.PROGRESS_MEDIA_ID] * image_count
        if is_new:
            self.send_card(progress, images, elapse_seconds, incoming_message)
        else:
            self.update_card(progress, images, elapse_seconds, incoming_message)


    def reply_markdown(self, images, elapse_seconds, incoming_message):
        if len(images) == 0:
            self.logger.error('empty image list')
            return
        image_content = self._merge_images(images)
        media_id = self.dingtalk_client.upload_to_dingtalk(image_content)
        title = 'Stable Diffusion Bot'
        content = ('#### Prompt: %s\n\n'
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
        self.send_markdown(title, content, incoming_message)

    def send_markdown(self, title, content, incoming_message: dingtalk_stream.ChatbotMessage):
        request_headers = {
            'Content-Type': 'application/json',
            'Accept': '*/*',
        }
        values = {
            'msgtype': 'markdown',
            'markdown': {
                'title': title,
                'text': content,
            },
            'at': {
                'atUserIds': [incoming_message.sender_staff_id],
            }
        }
        try:
            response = requests.post(incoming_message.session_webhook,
                                     headers=request_headers,
                                     data=json.dumps(values))
            response.raise_for_status()
        except Exception as e:
            self.logger.error('reply markdown failed, error=%s', e)
            return None
        return response.json()

    def reply_card(self, images, elapse_seconds, incoming_message: dingtalk_stream.ChatbotMessage):
        card_id = self._gen_card_id(incoming_message)
        medias = [self.upload_image(i) for i in images]
        result = self.update_card(None, medias, elapse_seconds, incoming_message)
        if result == 403:
            # downgrade to markdown
            self.reply_markdown(images, elapse_seconds, incoming_message)

    def send_card(self, progress, images, elapse_seconds, incoming_message: dingtalk_stream.ChatbotMessage):
        card_id = self._gen_card_id(incoming_message)
        card_data = self.get_card_data(progress, images, elapse_seconds, incoming_message)
        request_headers = {
            'Content-Type': 'application/json',
            'x-acs-dingtalk-access-token': self.dingtalk_client.get_access_token(),
            'Accept': '*/*',
        }
        values = {
            'cardTemplateId': 'StandardCard',
            'openConversationId': incoming_message.conversation_id,
            # 'singleChatReceiver': json.dumps({'userId': incoming_message.sender_staff_id}),
            'cardBizId': card_id,
            'robotCode': incoming_message.robot_code,
            'cardData': json.dumps(card_data),
            'sendOptions': {
                'atUserListJson': json.dumps([{
                    'nickName': incoming_message.sender_nick,
                    'userId': incoming_message.sender_staff_id,
                }]),
            }
        }
        url = 'https://api.dingtalk.com/v1.0/im/v1.0/robot/interactiveCards/send'
        try:
            response = requests.post(url,
                                     headers=request_headers,
                                     data=json.dumps(values))
            response.raise_for_status()
        except Exception as e:
            self.logger.error('send card failed, error=%s, response=%s', e, response.text)
            return response.status_code
        return response.json()

    def update_card(self, progress, images, elapse_seconds, incoming_message: dingtalk_stream.ChatbotMessage):
        card_id = self._gen_card_id(incoming_message)
        card_data = self.get_card_data(progress, images, elapse_seconds, incoming_message)
        print('progress:', progress)
        print('incoming_message:', incoming_message)
        print('card_id:', card_id)
        print('card_data:', card_data)
        request_headers = {
            'Content-Type': 'application/json',
            'x-acs-dingtalk-access-token': self.dingtalk_client.get_access_token(),
            'Accept': '*/*',
        }
        values = {
            'cardBizId': card_id,
            'cardData': json.dumps(card_data),
        }
        url = 'https://api.dingtalk.com/v1.0/im/robots/interactiveCards'
        try:
            response = requests.put(url,
                                     headers=request_headers,
                                     data=json.dumps(values))
            response.raise_for_status()
        except Exception as e:
            self.logger.error('update card failed, error=%s, response=%s', e, response.text)
            return response.status_code
        return response.json()

    @staticmethod
    def get_card_data(progress, images, elapse_seconds, incoming_message):
        contents = []
        if progress:
            contents.append({
                "type": "text",
                "text": "处理中，进度 %s ..." % progress,
                "id": "text_1685500462094"
            })
        contents.append({
            "type": "text",
            "text": "Prompt: %s" % incoming_message.text.content.strip(),
            "id": "text_1685432118811"
        })
        contents.append({
            "type": "imageList",
            "images": images,
            "id": "imageList_1685500414369"
        })
        contents.append({
            "type": "markdown",
            "text": ("> Elapse %ss\n> Powered by "
                     "[https://github.com/chzealot/dingtalk-stable-diffusion]"
                     "(https://github.com/chzealot/dingtalk-stable-diffusion)"
                     ) % round(elapse_seconds, 3),
            "id": "markdown_1685516479734"
        })
        card_data = {
            "config": {
                "autoLayout": True,
                "enableForward": True
            },
            "header": {
                "title": {
                    "type": "text",
                    "text": "Stable Diffusion Bot"
                },
                "logo": "@lALPDtXaA1csu9g4MA"
            },
            "contents": contents
        }
        return card_data

    def upload_image(self, image_obj):
        fp = io.BytesIO()
        image_obj.save(fp, 'PNG')
        content = fp.getvalue()
        return self.dingtalk_client.upload_to_dingtalk(content)

    @staticmethod
    def _gen_card_id(msg: dingtalk_stream.ChatbotMessage):
        factor = '%s_%s_%s_%s' % (msg.sender_id, msg.sender_corp_id, msg.conversation_id, msg.message_id)
        m = hashlib.sha256()
        m.update(factor.encode('utf-8'))
        return m.hexdigest()

    @staticmethod
    def _merge_images(images):
        fp = io.BytesIO()
        if len(images) == 1:
            images[0].save(fp, 'PNG')
            return fp.getvalue()
        if len(images) == 4:
            width, height = images[0].size

            img_merge = Image.new('RGB', (width * 2, height * 2))
            img_merge.paste(images[0], (0, 0))
            img_merge.paste(images[1], (width, 0))
            img_merge.paste(images[2], (0, height))
            img_merge.paste(images[3], (width, height))
            img_merge.save(fp, 'PNG')
            return fp.getvalue()
        return b''
