# dingtalk-stable-diffusion
A DingTalk chatbot with stable diffusion

支持能力

* 单聊
* 群聊（AT 机器人）

## 使用说明：Google colab环境

### 准备材料


1. 钉钉开发者账号，具备创建企业内部应用的权限，详见[成为钉钉开发者](https://open.dingtalk.com/document/orgapp/become-a-dingtalk-developer)
2. Google colab账号

步骤

1. 参考[DingTalk Stream Mode 介绍](https://github.com/open-dingtalk/dingtalk-stream-sdk-python)创建企业内部应用，获得 ClientID（即 AppKey）和 ClientSecret（即 AppSecret），并创建机器人，申请发消息权限（权限点Code为qyapi_robot_sendmsg），确认并发布应用
2. 打开 Google colab：https://colab.research.google.com/github/chzealot/dingtalk-stable-diffusion/blob/main/dingtalk_stable_diffusion.ipynb
3. 在 "put-your-dingtalk-client-id-here" 和 "put-your-dingtalk-client-secret-here" 处，填入步骤1中的 ClientID 和 ClientSecret
4. 执行 Google colab 中的代码

**温馨提醒：**

1. 需要在钉钉开发者后台，为机器人应用申请 "企业内机器人发送消息权限"（权限点 Code 为 qyapi_robot_sendmsg），否则会出现功能降级（发送markdown消息，而不是卡片），不支持进度更新 
2. 如果是从其他地方 copy 到 colab 的代码，务必将运行时类型中硬件加速器改为 GPU（菜单栏-代码执行程序-更改运行时类型）


至此，钉钉 Stable Diffusion 机器人已经创建完成，可以在群里体验了。有两种方式：

1. 开发者后台中，左侧导航"消息推送"，有"点击调试"，会自动创建群，并将机器人安装进去，群内 AT 机器人即可
2. 企业内部群中，添加机器人

![效果展示](https://pic.peo.pw/a/2023/05/16/64635924b7adb.png)

## 使用说明：Mac 本地环境

跟上面的 Google colab 环境流程类似，区别在于启动参数：

```shell
$ pip install -r requirements.txt
$ python dingtalksd.py \
    --client_id="put-your-dingtalk-client-id-here" \
    --client_secret="put-your-dingtalk-client-secret-here"
```

## 参考资料
