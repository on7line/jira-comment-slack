# -*- coding: utf-8 -*-
import json
import logging
import os
import requests

from flask import Flask, request, jsonify

from logging.handlers import RotatingFileHandler, SysLogHandler

app = Flask(__name__)

try:
    config = json.load(open('/etc/jira_comment_slack.conf.json', 'r'))
    # Mandatory settings
    slack_url = config['slack_url']
    slack_channel = config['channel']

    # Optional settings
    slack_post = config.get('slack_post', True)
    flask_host = config.get('host', '127.0.0.1')
    flask_port = config.get('port', 11000)
    flask_logfile = config.get('logfile', None)
    flask_logaddress = config.get('syslog_address', '/dev/log')
    flask_debug = config.get('debug', False)
except IOError as ex:
    raise IOError('Open config file error, please create new config file. %s' % ex)


class JiraSysLogHandler(SysLogHandler):

    def __init__(self, *args, **kwargs):
        kwargs.update({
            'address': flask_logaddress
        })
        super(JiraSysLogHandler, self).__init__(*args, **kwargs)
        self.formatter = logging.Formatter(fmt='%(ident)s %(levelname)s: %(message)s')

    def emit(self, record):
        record.ident = 'JiraCommentSlack[%s]:' % os.getpid()
        super(JiraSysLogHandler, self).emit(record)


@app.route('/webhook', methods=['GET', 'POST'])
def tracking():
    if request.method == 'POST':
        rd = request.get_json()
        issue_event_type_name = rd['issue_event_type_name']
        if 'changelog' in rd:
            inkey = ['Attachment','Sprint','Rank']
            from_value = rd['changelog']['items'][0]['from']
            to_value = rd['changelog']['items'][0]['to']
            field = rd['changelog']['items'][0]['field']
            fromString = rd['changelog']['items'][0]['fromString']
            toString = rd['changelog']['items'][0]['toString']
            displayName = rd['user']['displayName']
            event_type = issue_event_type_name
            changed_body = "Change field:%s from:%s to:%s\n" %(field,fromString,toString)
            slack_color = "#8FBC8F"
            if field in inkey:
                print("key:%s return\n" %(field))
                data = jsonify(rd)
                return data
            if field == "assignee":
                event_type = "changed assignee"
                slack_color = "#ffeb3b" 
                changed_body = "%s -> %s \n" % (fromString,toString)
            if field == "resolution":
                if toString == "Done":
                    slack_color = "#cddc39"
                if toString == "None":
                    slack_color = "#3f51b5"
                changed_body = "%s -> %s \n" % (fromString,toString)
                event_type = "changed resolution"
            if field == "status":
                event_type = "changed status"
                slack_color = "#00BFFF"
                if toString == "In Progress":
                    slack_color = "#2196f3"
                if toString == "In Code Review":
                    slack_color = "#4caf50"
                if toString == "In Review":
                    slack_color = "#009688"
                if toString == "Done":
                    slack_color ="#cddc39"
                if toString == "To Do":
                    slack_color = "#607d8b"
                changed_body = "%s -> %s \n" % (fromString,toString)

            task_key = rd['issue']['key']
            task_id = rd['issue']['id']
            task_link = str(rd['issue']['self']).replace('rest/api/2/issue', 'browse').replace(task_id, task_key)
            task_summary = rd['issue']['fields']['summary']
            slack_pretext = displayName + ' ' + event_type
            slack_title = task_key + " : " + task_summary
            slack_data = {
                "username": "JIRA Changed ",
                "channel": slack_channel,
                "attachments": [
                    {
                        "fallback": slack_pretext + " - " + slack_title + " - " + task_link,
                        "pretext": slack_pretext,
                        "title": slack_title,
                        "title_link": task_link,
                        "text": changed_body,
                        "color": slack_color
                    }
                ]
            }
            if slack_post:
                post(slack_data)
            else:
                app.logger.warn('Slack posting was disabled by config')
        if issue_event_type_name == 'issue_created':
            event_type = 'Issue created'
            changed_body = ""
            slack_color = "#F44336" 

            task_key = rd['issue']['key']
            task_id = rd['issue']['id']
            task_link = str(rd['issue']['self']).replace('rest/api/2/issue', 'browse').replace(task_id, task_key)
            task_summary = rd['issue']['fields']['summary']
            displayName = rd['user']['displayName']
            slack_pretext = displayName + ' ' + event_type
            slack_title = task_key + " : " + task_summary
            slack_data = {
                "username": "JIRA Changed ",
                "channel": slack_channel,
                "attachments": [
                    {
                        "fallback": slack_pretext + " - " + slack_title + " - " + task_link,
                        "pretext": slack_pretext,
                        "title": slack_title,
                        "title_link": task_link,
                        "text": changed_body,
                        "color": slack_color
                    }
                ]
            }
            if slack_post:
                post(slack_data)
            else:
                app.logger.warn('Slack posting was disabled by config')
        if 'comment' in rd:
            comment_body = rd['comment']['body']
            comment_author = rd['comment']['updateAuthor']['displayName']
            comment_id = rd['comment']['id']

            if rd['comment']['created'] == rd['comment']['updated']:
                comment_type = 'created'
                slack_color = '#439FE0'
            else:
                comment_type = 'updated'
                slack_color = '#7CD197'

            task_key = rd['issue']['key']
            task_id = rd['issue']['id']
            task_link = str(rd['issue']['self']).replace('rest/api/2/issue', 'browse').replace(task_id, task_key)
            task_summary = rd['issue']['fields']['summary']

            comment_link = ('%(task_link)s?focusedCommentId=%(comment_id)s&'
                            'page=com.atlassian.jira.plugin.system.issuetabpanels:'
                            'comment-tabpanel#comment-%(comment_id)s') % {
                'task_link': task_link,
                'comment_id': comment_id,
            }

            slack_pretext = comment_author + ' ' + comment_type + ' comment'
            slack_title = task_key + ' : ' + task_summary
            slack_data = {
                'username': 'JIRA Comment',
                'channel': slack_channel,
                'attachments': [
                    {
                        'fallback': slack_pretext + ' - ' + slack_title + ' - ' + comment_link,
                        'pretext': slack_pretext,
                        'title': slack_title,
                        'title_link': comment_link,
                        'text': comment_body,
                        'color': slack_color
                    }
                ]
            }
            if slack_post:
                post(slack_data)
            else:
                app.logger.warn('Slack posting was disabled by config')


        data = jsonify(rd)
        return data
    else:
        app.logger.info(request)
        return 'It Works!'  # Imitating Apache?

def post(data):
    response = requests.post(
        slack_url, data=json.dumps(data),
        headers={'Content-Type': 'application/json'}
    )
    app.logger.info(data)
    if response.status_code != 200:
        raise ValueError(
            "Request to slack meets error %s, the response is:\n%s"
            % (response.status_code, response.text)
        )
def main():
    if flask_logfile:
        handler = RotatingFileHandler(flask_logfile, maxBytes=10000, backupCount=1)
    else:
        handler = JiraSysLogHandler()

    app.logger.addHandler(handler)
    app.logger.setLevel(logging.DEBUG if flask_debug else logging.INFO)
    app.run(debug=flask_debug, host=flask_host, port=flask_port, passthrough_errors=True)


if __name__ == '__main__':
    main()
