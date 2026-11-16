from html.parser import HTMLParser
import unittest
from app.services.bot_menu import caption_pages, utf16_length, with_navigation


class VisibleText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text=''
        self.tags=[]
    def handle_data(self,data):self.text+=data
    def handle_starttag(self,tag,attrs):self.tags.append(tag)
    def handle_endtag(self,tag):
        if not self.tags or self.tags.pop()!=tag:raise AssertionError('Unbalanced HTML page')


class CaptionNavigationTests(unittest.TestCase):
    def test_long_nested_html_preserves_all_text_links_and_balanced_tags(self):
        body='<b>'+('Текст &amp; детали 😀 '*150)+'<a href="https://example.invalid/help"><i>'+('Ссылка '*250)+'</i></a></b>'
        original=VisibleText();original.feed(body)
        visible=[]
        for page,mode in caption_pages(body):
            self.assertEqual(mode,'HTML')
            parser=VisibleText();parser.feed(page)
            self.assertEqual(parser.tags,[])
            self.assertLessEqual(utf16_length(parser.text),1000)
            visible.append(parser.text)
            if '<a ' in page:self.assertIn('href="https://example.invalid/help"',page)
        self.assertEqual(''.join(visible),original.text)

    def test_emoji_at_last_unit_does_not_hang_or_split_surrogates(self):
        body='<b>'+'x'*999+'😀'+'y'*1000+'</b>'
        pages=caption_pages(body)
        text=''
        for part,_ in pages:
            parser=VisibleText();parser.feed(part)
            self.assertLessEqual(utf16_length(parser.text),1000)
            text+=parser.text
        self.assertEqual(text,'x'*999+'😀'+'y'*1000)

    def test_single_page_keeps_original_html(self):
        self.assertEqual(caption_pages('<b>Инструкция</b>'),[('<b>Инструкция</b>','HTML')])

    def test_pagination_callbacks_fit_telegram_limit_and_back_is_last(self):
        prefix='guide:'+'a'*40
        markup=with_navigation(None,prefix,1,5,back=True)
        self.assertEqual(markup['inline_keyboard'][-1],[{'text':'← Назад','callback_data':'bot:home'}])
        for row in markup['inline_keyboard']:
            for button in row:self.assertLessEqual(len(button['callback_data'].encode()),64)
