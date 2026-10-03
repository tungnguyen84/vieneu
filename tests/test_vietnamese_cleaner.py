import pytest
from apps.script_factory.vietnamese_cleaner import clean_garbled_vietnamese, find_garbled_vietnamese_issues


def test_clean_english_numbers():
    text = "một kế toán viên thirty-two tuổi ở thành phố"
    assert clean_garbled_vietnamese(text) == "một kế toán viên ba mươi hai tuổi ở thành phố"
    assert len(find_garbled_vietnamese_issues(text)) == 1
    assert len(find_garbled_vietnamese_issues(clean_garbled_vietnamese(text))) == 0


def test_clean_stray_consonants():
    text = "những bí mật r âm ỉ đằng sau gia tộc"
    assert clean_garbled_vietnamese(text) == "những bí mật âm ỉ đằng sau gia tộc"
    assert len(find_garbled_vietnamese_issues(text)) == 1
    assert len(find_garbled_vietnamese_issues(clean_garbled_vietnamese(text))) == 0


def test_clean_stuttered_syllables():
    text = "Sau vài lần xoayay chiếc chìa khóa nhỏ"
    assert clean_garbled_vietnamese(text) == "Sau vài lần xoay chiếc chìa khóa nhỏ"
    assert len(find_garbled_vietnamese_issues(text)) == 1
    assert len(find_garbled_vietnamese_issues(clean_garbled_vietnamese(text))) == 0


def test_clean_audio_typos():
    assert clean_garbled_vietnamese("tay chị chợ khựng lại") == "tay chị chợt khựng lại"
    assert clean_garbled_vietnamese("miệng ngậm điếu thuốc tút dở") == "miệng ngậm điếu thuốc hút dở"


def test_valid_acronyms_and_units_preserved():
    text = "Anh là CEO của công ty, đang kiểm tra kết nối Wi-Fi trong khoảng cách 10 m."
    assert clean_garbled_vietnamese(text) == text
    assert len(find_garbled_vietnamese_issues(text)) == 0
