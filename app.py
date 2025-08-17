from flask import Flask, render_template, request, jsonify
from bs4 import BeautifulSoup
import webview
import sys
import os
import chardet
from docx import Document
import markdown
import tempfile
import html

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 200 * 1024 * 1024  # Увеличено до 200MB

def detect_encoding(file_path):
    with open(file_path, 'rb') as f:
        result = chardet.detect(f.read())
    return result['encoding']

def extract_text_from_file(file):
    filename = file.filename.lower()
    temp_path = None

    try:
        # Сохраняем временный файл
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            file.save(tmp.name)
            temp_path = tmp.name

        if filename.endswith('.txt') or filename.endswith('.html'):
            encoding = detect_encoding(temp_path)
            with open(temp_path, 'r', encoding=encoding) as f:
                return f.read()

        elif filename.endswith('.docx'):
            doc = Document(temp_path)
            return '\n'.join([para.text for para in doc.paragraphs])

        elif filename.endswith('.doc'):
            # Для .doc файлов можно использовать python-docx2txt
            import docx2txt
            return docx2txt.process(temp_path)

        elif filename.endswith('.md'):
            encoding = detect_encoding(temp_path)
            with open(temp_path, 'r', encoding=encoding) as f:
                return markdown.markdown(f.read())
        else:
            # Пытаемся прочитать как текст
            encoding = detect_encoding(temp_path)
            with open(temp_path, 'r', encoding=encoding) as f:
                return f.read()
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)


def format_milliseconds_to_hms(ms):
    if ms is None:
        return ""
    try:
        total_seconds = int(ms) // 1000
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60

        # Форматируем с ведущими нулями
        if hours > 0:
            return f"[{hours:02}:{minutes:02}:{seconds:02}] "
        else:
            return f"[{minutes:02}:{seconds:02}] "
    except ValueError:
        return ""  # Если data-time не число


def parse_transcript(html_content):
    # The problem states that pasted text can cause errors.
    # This often happens because the text contains HTML entities like &lt; instead of <.
    # The html.unescape function is designed to fix this.
    # By running it unconditionally, we create a single, reliable processing path
    # for both file content (usually raw HTML) and pasted text (often escaped).
    # This function is safe to run on non-escaped HTML, as it will leave it unchanged.
    processed_content = html.unescape(html_content)

    # There's a chance the content is double-escaped (e.g., &amp;lt;).
    # Running unescape a second time can fix this. It's a low-cost operation.
    processed_content = html.unescape(processed_content)

    soup = BeautifulSoup(processed_content, 'html.parser')

    blocks = soup.find_all('p', class_='group/block')

    if not blocks:
        return "Не найдено блоков с расшифровкой (возможно, изменилась структура или код HTML экранирован)."

    result = []
    for block in blocks:
        # --- Извлечение имени спикера ---
        speaker_elem = block.find('span', {'data-speaker': 'true'})
        speaker = "Неизвестный"
        if speaker_elem:
            speaker_name_span = speaker_elem.find('span')
            if speaker_name_span:
                speaker = speaker_name_span.get_text(strip=True)

        # --- Извлечение и форматирование таймкода ---
        timestamp_ms = block.get('data-time')
        timestamp_formatted = format_milliseconds_to_hms(timestamp_ms)

        # --- Извлечение текста расшифровки с сохранением пробелов ---
        text_spans = block.find_all('span', {'data-clipped': 'false'})

        text_parts = []
        for span in text_spans:
            part = span.get_text(strip=True)
            if part:
                text_parts.append(part)

        text = " ".join(text_parts).strip()

        if text:
            result.append(f"{timestamp_formatted}{speaker}:\n{text}\n")

    return '\n'.join(result) if result else "Расшифровка не найдена."

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/process', methods=['POST'])
def process():
    try:
        # Теперь все входные данные обрабатываются как файлы, чтобы обойти ошибку 413
        if 'file' in request.files and request.files['file'].filename:
            file = request.files['file']
            content = extract_text_from_file(file)
        else:
            return jsonify({'error': 'Нет данных для обработки'}), 400

        # Парсим контент
        result = parse_transcript(content)
        return jsonify({'result': result})

    except Exception as e:
        return jsonify({'error': f'Ошибка обработки: {str(e)}'}), 500

def get_resource_path(relative_path):
    """ Получить путь к ресурсу для PyInstaller """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'debug':
        app.run(debug=True)
    else:
        window = webview.create_window(
            'Расшифровщик встреч из tl;dv',
            app,
            width=900,
            height=700,
            min_size=(600, 500)
        )
        webview.start()