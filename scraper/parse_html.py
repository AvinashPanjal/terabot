from html.parser import HTMLParser

class ClickableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []
        self.current_tag = None

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        # We care about button, a, div, span with classes or ids
        if tag in ['a', 'button'] or 'btn' in attrs_dict.get('class', '') or 'download' in attrs_dict.get('class', ''):
            self.current_tag = {
                'tag': tag,
                'attrs': attrs_dict,
                'text': ''
            }
            self.tags.append(self.current_tag)

    def handle_endtag(self, tag):
        if self.current_tag and self.current_tag['tag'] == tag:
            self.current_tag = None

    def handle_data(self, data):
        if self.current_tag:
            self.current_tag['text'] += data.strip()

with open('terabox_rendered.html', 'r', encoding='utf-8') as f:
    html = f.read()

parser = ClickableParser()
parser.feed(html)

with open('parse_html_out.txt', 'w', encoding='utf-8') as out_f:
    for item in parser.tags:
        if item['text'] or 'class' in item['attrs'] or 'id' in item['attrs']:
            out_f.write(f"Tag: {item['tag']} | Attrs: {item['attrs']} | Text: {item['text']}\n")
