# i18n 骨架测试：不 boot Flask app，直接装载 mo 断言翻译
import os

from babel.support import Translations

BASE = os.path.join(os.path.dirname(__file__), '..', 'myapp', 'translations')

# 首批翻译稳定键（home.py 菜单树，与实施时填入 en po 的翻译映射一致）
STABLE_KEYS = {
    '数据资产': 'Data Assets',
    '数据探索': 'Data Explorer',
    '数据集': 'Datasets',
}


def test_en_mo_exists_and_loadable():
    mo = os.path.join(BASE, 'en', 'LC_MESSAGES', 'messages.mo')
    assert os.path.exists(mo), f'missing {mo}, run scripts/i18n_compile.sh'
    translations = Translations.load(dirname=BASE, locales=['en'])
    for src, expect in STABLE_KEYS.items():
        assert translations.gettext(src) == expect


def test_zh_fallback_keeps_source():
    # 无 zh catalog 时应回退源语言中文（返回原文即视为回退成功）
    translations = Translations.load(dirname=BASE, locales=['zh'])
    assert translations.gettext('数据资产') == '数据资产'
