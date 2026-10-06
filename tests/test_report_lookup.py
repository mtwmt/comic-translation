import json
import os
import pytest
from pathlib import Path

from src.offline.report_lookup import find_source_report


def report(path, source, timestamp):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({'source':str(source), 'source_hash':'fixture', 'image_size':[20,20], 'regions':[]}))
    os.utime(path, (timestamp,timestamp))
    return path


def test_latest_retry_and_revision_match_exact_source_not_filename(tmp_path):
    source = tmp_path/'a'/'page.jpg'
    other = tmp_path/'b'/'page.jpg'
    work = tmp_path/'outputs'/'work'
    old = report(work/'page_繁中.json',source,100)
    retry = report(work/'page_繁中_2.json',source,200)
    assert find_source_report(source,[old]) == retry
    revised = report(work/'page_繁中_2_修訂.json',source,300)
    report(work/'other.json',other,400)
    assert find_source_report(source,[old]) == revised
    assert find_source_report(other,[old]) == work/'other.json'


@pytest.mark.parametrize('folder', ['work'])
def test_readded_nested_source_finds_report_without_batch_index(tmp_path, folder):
    root = tmp_path/'book'
    source = root/'chapter'/'page.jpg'
    expected = report(root/'translated'/'chapter'/folder/'page_zh-TW.json',source,100)
    assert find_source_report(source, source_root=root) == expected


def test_missing_corrupt_or_batch_json_does_not_open_another_picture(tmp_path):
    source = tmp_path/'page.jpg'
    directory = tmp_path/'translated'/'work'
    other = report(directory/'another.json', tmp_path/'different.jpg', 100)
    (directory/'corrupt.json').write_text('{')
    (directory/'batch.json').write_text(json.dumps({'source':str(source),'pages':[]}))
    assert find_source_report(source,[directory/'missing.json']) is None
    assert other.exists()
