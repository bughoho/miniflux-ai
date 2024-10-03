import concurrent.futures
import time
import logging
import traceback
import xml.etree.ElementTree as ET
import xml.sax.saxutils as saxutils

import html2text

import miniflux
from markdownify import markdownify as md
import markdown
from openai import OpenAI
from yaml import safe_load

import mistune
from mistune.renderers.markdown import MarkdownRenderer
from mistune.renderers.markdown import BlockState

from mistune.plugins.task_lists import task_lists
#from mistune.plugins.table import table
from custom_table import table
import re
import signal
import sys

from markdown.extensions.tables import TableExtension
extensions = [
    'markdown.extensions.extra',
    'markdown.extensions.codehilite',
    'markdown.extensions.toc',
    'markdown.extensions.tables',
    'markdown.extensions.fenced_code',
]

config = safe_load(open('config.yml', encoding='utf8'))
miniflux_client = miniflux.Client(config['miniflux']['base_url'], api_key=config['miniflux']['api_key'])
llm_client = OpenAI(base_url=config['llm']['base_url'], api_key=config['llm']['api_key'])

logger = logging.getLogger(__name__)
logger.setLevel(config.get('log_level', 'INFO'))
formatter = logging.Formatter('%(asctime)s - %(filename)s - %(lineno)d - %(levelname)s - %(message)s')
console = logging.StreamHandler()
console.setFormatter(formatter)
logger.addHandler(console)

def signal_handler(signal, frame):
    print('You pressed Ctrl+C!')
    sys.exit(0)
    

def escape_text(match):
    # 获取匹配到的文本内容
    content = match.group(2)
    # 对文本进行转义编码
    escaped_content = saxutils.escape(content)
    return f'<content id="{match.group(1)}">{escaped_content}</content>'

def replace_and_escape(input_text):
    # 使用正则表达式查找 <content id=x>文本</content>
    pattern = r'<content id="(\d+)">(.*?)</content>'
    # 使用 re.sub 替换文本
    result = re.sub(pattern, lambda m: escape_text(m), input_text)
    return result

class CustomRenderer(MarkdownRenderer):
    def __init__(self,agent):
        super().__init__()
        self.agent = agent
        self.is_sublist = False
        self.stop_collection()
        
    def dict_to_xml(self,data):
        """将字典转换为 XML 字符串"""
        root = ET.Element('root')  # 创建根元素
        chars_string = "".join(['<','>','&'])
        for key, value in data.items():
            item = ET.SubElement(root, 'content', id=str(key))  # 创建子元素并添加属性
            if any(s in value for s in ['<','>','&']):
              pass
            #item.text = saxutils.escape(value)  # 设置文本内容
            item.text = value
        return ET.tostring(root, encoding='unicode')  # 转换为字符串并返回
    
    def xml_to_dict(self,xml_string,original_map):
        """将 XML 字符串解析为字典"""
        try:
            new_xml_string = replace_and_escape(xml_string)
            root = ET.fromstring(new_xml_string)  # 解析 XML 字符串
            for child in root:
                if child.text == None:
                    original_text = original_map[int(child.attrib['id'])]
                    if len(original_text) <= 4:
                        child.text = original_text
                    pass
                
            return {child.attrib['id']: child.text for child in root}  # 构建字典
        except ET.ParseError:
            return None  # 解析失败时返回 None

    def render_tokens(self, tokens, state):
        try:
            return ''.join(self.iter_tokens(tokens, state))
        except:
            return ''
    def iter_tokens(self, tokens, state):
        for token in tokens:
            result = self.render_token(token, state)  # 假设这是处理每个 token 的方法
            if result is not None:
                yield result  # 确保只生成有效的结果
            else:
                pass
            
    def translate(self, text,prompt=''):
        if len(text) < 6:
            return text
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": text }
        ]
        completion = llm_client.chat.completions.create(
            model=config['llm']['model'],
            messages= messages,
            temperature= config.get('llm', {}).get('temperature', None),
            timeout=config.get('llm', {}).get('timeout', 120)
        )
        response_content = completion.choices[0].message.content
        logger.info(f"{response_content}\n")
        
        if response_content.find('<content') != -1:
            return response_content
        return text
    
    def translate_map(self,map,prompt=''):
        for i in range(5):
            xml_string = self.dict_to_xml(map)
            response_content = self.translate(xml_string,prompt)
            parsed_map = self.xml_to_dict(response_content,map)
            if parsed_map != None and len(parsed_map)>0:
                for key, value in parsed_map.items():
                    parsed_map[key] = saxutils.unescape(value) if value != None else value
                    
                # 如果有有没有翻译的内容，迭代继续翻译
                remain_map = {}
                for key,value in map.items():
                    if str(key) not in parsed_map or parsed_map[str(key)] == None:
                        remain_map[key] = saxutils.unescape(value)
                        pass
                if len(remain_map) > 0:
                    translated_remain_map = self.translate_map(remain_map,prompt)
                    if len(translated_remain_map) > 0:
                        parsed_map.update(translated_remain_map)
                return parsed_map
            else:
                pass
        return None
        
    def translate_collection(self):
        prompt = self.agent[1].get('collection_prompt',None)
        copyMap =self.original_map.copy()
        self.translated_map = self.translate_map(copyMap,prompt)
        return
    
    def blank_line(self, token, state):
        newtoken = token
        return super().blank_line(newtoken, state)
    def start_collection(self):
        self.original_map = {}
        self.translated_map = {}
        self.collection_flag = True
        self.replace_translated = False
    def stop_collection(self):
        self.original_map = {}
        self.translated_map = {}
        self.collection_flag = False
        self.replace_translated = False
    def append_collection_text(self,text):
        self.original_map[len(self.original_map)] = text
    def paragraph(self, token, state):
        # content = super().paragraph(token, state)
        self.start_collection()
        content = super().paragraph(token, state)
        print(content)
        if len(self.original_map) > 0:
            self.translate_collection()
        if self.translated_map != None and len(self.translated_map) > 0:
            self.collection_flag = False
            self.replace_translated = True #开始替换字符串
            self.cur_index = 0
            if content.find("Discord Follow") != -1:
                pass
            content = super().paragraph(token, state)
        
        self.stop_collection()
        return content
    
    def heading(self, token, state):
        # content = super().heading(token, state)
        
        self.start_collection()
        content = super().heading(token, state)
        print(content)
        if len(self.original_map) > 0:
            self.translate_collection()
        if self.translated_map != None and len(self.translated_map) > 0:
            self.collection_flag = False
            self.replace_translated = True #开始替换字符串
            self.cur_index = 0
            content = super().heading(token, state)
        self.stop_collection()
        return content
    def table(self, token,state):
        self.start_collection()
        content = self.render_children(token, state)
        print(content)
        if len(self.original_map) > 0:
            self.translate_collection()
        if self.translated_map != None and len(self.translated_map) > 0:
            self.collection_flag = False
            self.replace_translated = True #开始替换字符串
            self.cur_index = 0
            content = self.render_children(token, state)
        self.stop_collection()
        return content + '\n\n'
    
    def table_bottomline(self,rowcount):
        return '|' + '--- | ' * rowcount
    
    def render_table_children(self, token, state: BlockState):
        children = token['children']
        return self.render_table_tokens(children, state)
    def render_table_tokens(self, tokens, state):
        return ' | '.join(self.iter_tokens(tokens, state))
    
    
    def table_head(self, token, state):
        content = self.render_table_children(token, state)
        rowlen = len(token['children'])
        separator = self.table_bottomline(rowlen)
        return '| ' + content + ' |' + '\n' + separator + '\n'
    def table_body(self, token, state):
        content = self.render_children(token, state)
        rowlen = len(token['children'])
        return content + '\n'
    def table_row(self, token, state):
        content = self.render_table_children(token, state)
        return '| ' + content + ' |' +'\n'
    def table_cell(self, token, state, ):
        content = self.render_children(token, state)
        return content
    def list(self, token, state):
        # content = super().list(token, state)
        if not self.is_sublist:
            self.is_sublist = True #执行super().list时可能产生迭代
            self.start_collection()
            content = super().list(token, state)
            print(content)
            if len(self.original_map) > 0:
                self.translate_collection()
            if self.translated_map != None and len(self.translated_map) > 0:
                self.collection_flag = False
                self.replace_translated = True #开始替换字符串
                self.cur_index = 0
                content = super().list(token, state)
            self.stop_collection()
            
            self.is_sublist = False
        else:
            #现在迭代到的是子列表，直接执行即可
            content = super().list(token, state)
        return content
    def list_item(self, token, state):
        newtoken = token
        content = self.render_children(token, state)
        return content
    def link(self, token, state):
        content = super().link(token,state)
        return content
    def image(self, token, state):
        content = super().image(token,state)
        return content
    def text(self, token, state):
        newtoken = token
        count = sum(1 for char in token['raw'] if char.isalpha())
        if count <= 2:
            return super().text(newtoken, state)
        
        if self.replace_translated:
            #开始替换字符串
            if str(self.cur_index) in self.translated_map:
                content = self.translated_map[str(self.cur_index)]
            else:
                pass
            self.cur_index = self.cur_index+1
            return content
            
        if self.collection_flag:
            content = super().text(newtoken, state)
            self.append_collection_text(content)
        return super().text(newtoken, state)

def process_md_content(agent,html_content):
    #md_content = html2text.html2text(html_content)
    md_content = md(html_content,keep_inline_images_in=['a'])
    parser = mistune.Markdown(renderer=CustomRenderer(agent),plugins=[table,task_lists])
    result,_ = parser.parse(md_content)
    return result

def process_entry(entry):
    llm_result = ''
    start_with_list = [name[1]['title'] for name in config['agents'].items()]
    style_block = [name[1]['style_block'] for name in config['agents'].items()]
    [start_with_list.append('<pre') for i in style_block if i]

    for agent in config['agents'].items():
        # # 打开文件并读取内容
        # with open("output.txt", "r", encoding="utf-8") as file:
        #     # 读取文件内容
        #     text = file.read()
        # with open("md.txt", "w", encoding="utf-8") as file:
        #             # 写入字符串到文件
        #             file.write(md(text))
        # output = process_md_content(agent,md(text))
        # with open("new.txt", "w", encoding="utf-8") as file:
        #             # 写入字符串到文件
        #             file.write(output)
                    
        
        # with open("newhtml.html", "w", encoding="utf-8") as file:
        #             # 写入字符串到文件
        #             file.write(markdown.markdown(output,extensions=extensions))

        # Todo Compatible with whitelist/blacklist parameter, to be removed
        allow_list = agent[1].get('allow_list') if agent[1].get('allow_list') is not None else agent[1].get('whitelist')
        deny_list = agent[1]['deny_list'] if agent[1].get('deny_list') is not None else agent[1].get('blacklist')

        title_messages = [
            {"role": "system", "content": agent[1]['title_prompt']},
            {"role": "user", "content": entry['title']}
        ]
        # messages = [
        #     {"role": "system", "content": agent[1]['prompt']},
        #     {"role": "user", "content": md(entry['content']) }
        # ]
        # filter, if AI is not generating, and in allow_list, or not in deny_list
        # if (entry['title'] == 'tw93/Pake' and
        if ((not entry['content'].startswith(tuple(start_with_list))) and
                (((allow_list is not None) and (entry['feed']['feed_url'] in allow_list)) or
                 (deny_list is not None and entry['feed']['feed_url'] not in deny_list) or
                 (allow_list is None and deny_list is None))):
            
            title_completion = llm_client.chat.completions.create(
                model=config['llm']['model'],
                messages= title_messages,
                temperature= config.get('llm', {}).get('temperature', None),
                timeout=config.get('llm', {}).get('timeout', 60)
            )
            response_title_content = title_completion.choices[0].message.content
            logger.info(f"\nagents:{agent[0]} \nfeed_title:{entry['title']} \nresult:{response_title_content}")

            response_content = process_md_content(agent,entry['content'])
            
            if agent[1]['style_block']:
                llm_result = (llm_result + '<pre style="white-space: pre-wrap;"><code>\n'
                              + agent[1]['title'] + '：'
                              + response_content.replace('\n', '').replace('\r', '')
                              + '\n</code></pre><hr><br />')
            else:
                llm_result = llm_result + f"{agent[1]['title']}：{markdown.markdown(response_content,extensions=extensions)}<hr><br />"

    if len(llm_result) > 0:
        original_html = '<details>\n<summary>原文内容</summary>\n\n' + entry['content'] + '\n\n</details>\n\n'
        miniflux_client.update_entry(entry['id'], title=response_title_content, content= llm_result + original_html)

# htmltable = markdown.markdown(md_table,extensions=[TableExtension()])
# print(htmltable)

signal.signal(signal.SIGTERM, signal_handler)
while True:
    try:
        config = safe_load(open('config.yml', encoding='utf8'))
        entries = miniflux_client.get_entries(status=['unread'], limit=10000)
        start_time = time.time()
        logger.info('Fetched unread entries: ' + str(len(entries['entries']))) if len(entries['entries']) > 0 else logger.info('No new entries')

        with concurrent.futures.ThreadPoolExecutor(max_workers=config.get('llm', {}).get('max_workers', 4)) as executor:
            futures = [executor.submit(process_entry, i) for i in entries['entries']]
            for future in concurrent.futures.as_completed(futures):
                try:
                    data = future.result()
                except Exception as e:
                    logger.error(traceback.format_exc())
                    logger.error('generated an exception: %s' % e)

        if len(entries['entries']) > 0 and time.time() - start_time >= 3:
            logger.info('Done')
        time.sleep(60)
    except Exception as e:
        logger.error(traceback.format_exc())
        logger.error('generated an exception: %s' % e)