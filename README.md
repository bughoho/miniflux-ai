# miniflux-ai

This project is a deep modification of[Qetesh/miniflux-ai](https://github.com/Qetesh/miniflux-ai),

主要修改如下:
1.The text paragraphs have been split into a list of texts, preserving the original HTML tags of the article to enhance readability.
2.The text is fed to the AI in segments to avoid issues with some lower-level AIs that cannot translate longer articles.

Miniflux with AI

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://github.com/user-attachments/assets/472306c8-cdd2-4325-8655-04ba7e6045e5">
  <source media="(prefers-color-scheme: light)" srcset="https://github.com/user-attachments/assets/ae99a06f-47b4-4de7-9373-4b82f5102b7e">
  <img align="right" alt="miniflux UI" src="https://github.com/user-attachments/assets/ae99a06f-47b4-4de7-9373-4b82f5102b7e" width="400" > 
</picture>

This project fetches RSS subscription content from Miniflux via API and utilizes a large language model (LLM) to generate summaries, translations, etc. The configuration file allows for easy customization and addition of LLM agents.

## Features

- **Miniflux Integration**: Seamlessly fetch unread entries from Miniflux.
- **LLM Processing**: Generate summaries, translations, etc. based on your chosen LLM agent.
- **Flexible Configuration**: Easily modify or add new agents via the `config.yml` file.
- **Markdown and HTML Support**: Outputs in Markdown or styled HTML blocks, depending on configuration.

## Requirements

- Python 3.11+
- Dependencies: Install via `pip install -r requirements.txt`
- Miniflux API Key
- API Key compatible with OpenAI-compatible LLMs (e.g., Ollama for LLaMA 3.1)

## Configuration

The repository includes a template configuration file: `config.sample.yml`. Modify the `config.yml` to set up:

- **Miniflux**: Base URL and API key.
- **LLM**: Model settings, API key, and endpoint.Add timeout, max_workers parameters due to multithreading
- **Agents**: Define each agent's prompt, allow_list/deny_list filters, and output style（`style_block` parameter controls whether the output is formatted as a code block in Markdown）.

Example `config.yml`:
```yaml
# INFO、DEBUG、WARN、ERROR
# INFO、DEBUG、WARN、ERROR
log_level: "INFO"

miniflux:
  base_url: http://192.168.1.225:183
  api_key: 

llm:
  base_url: https://open.bigmodel.cn/api/paas/v4/
  api_key: 
  model: glm-4-flash
  temperature: 0.3
  max_workers: 1

agents:
  translate:
    title: "AI 翻译"
    title_prompt: "翻译标题为中文，保留原语言的细微差别、语气和风格，不要添加任何解释或注释，标题中如果含有名称不要翻译。"
    collection_prompt: |-
      # 角色描述
      您是一位在科技和编程领域具有高度技能的多语言(支持英语、法语、俄语、西班牙语、葡萄牙语 等等)翻译专家，现在我将提供一段结构化的文本列表给你，请将文本准确翻译为中文，
      
      # 问题格式
      问题格式是一段xml结构文本：
      <root>
        <content id=1>this is a english text 1</content>
        <content id=2>this is a english text 2</content>
        <content id=3>this is a english text 3</content>
      </root>
      # 翻译格式
      翻译后的格式必须是xml结构，格式如下：
      <root>
        <content id=1>这是一段英文文本1</content>
        <content id=2>这是一段英文文本1</content>
        <content id=3>这是一段英文文本3</content>
      </root>

      #注意
      1.其中的id是文本的唯一标识，每个翻译结果都必须保证id正确。
      2.当要翻译的内容中含有html转义符时，翻译的结果要保持原来的html转义符。
      
    style_block: false
    deny_list:
    allow_list:
      - https://parsec.app/changelog.xml
```

## Docker Setup

The project includes a `docker-compose.yml` file for easy deployment:

```yaml
version: '3.3'
services:
    miniflux_ai:
        container_name: miniflux_ai
        image: onesbug/miniflux-ai:latest
        restart: always
        environment:
            TZ: Asia/Shanghai
        volumes:
            - ./config.yml:/app/config.yml
```

To start the service, run:

```bash
docker-compose up -d
```

## Usage

1. Ensure `config.yml` is properly configured.
2. Run the script: `python main.py`
3. The script will fetch unread RSS entries, process them with the LLM, and update the content in Miniflux.

## Contributing

Feel free to fork this repository and submit pull requests. Contributions are welcome!

## License

This project is licensed under the MIT License.
