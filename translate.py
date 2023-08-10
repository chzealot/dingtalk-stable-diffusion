#!/usr/bin/env python3

import logging
import urllib
import urllib.parse
import requests
import dingtalk_stream


class DingTalkTranslater(object):
    def __init__(self, logger: logging.Logger, dingtalk_client):
        self.logger = logger
        self.dingtalk_client = dingtalk_client

    def do_text_translate(self, query: str, source_language='zh', target_language='en'):
        access_token = self.dingtalk_client.get_access_token()
        if not access_token:
            self.logger.error('do_translate failed, cannot get dingtalk access token')
            return query

        values = {
            "query": query,
            "source_language": source_language,
            "target_language": target_language
        }
        text_translate_url = ('https://oapi.dingtalk.com/topapi/ai/mt/translate?access_token=%s'
                              ) % urllib.parse.quote_plus(access_token)
        try:
            response = requests.post(text_translate_url, data=values)
            if response.status_code == 401:
                self.dingtalk_client.reset_access_token()
            response.raise_for_status()
            if response.json()['errcode'] != 0:
                return query
        except Exception as e:
            self.logger.error('do text translate exception, error=%s', e)
            return query
        result = response.json()['result']
        self.logger.info('translate success, query=%s, result=%s', query, result)
        return result
