"""Additional offline regressions. All provider HTTP and speech calls are mocked.
FFmpeg, ffprobe, uploaded files, API routes and final MP4 validation run for real.
"""
from __future__ import annotations

import asyncio
import json
import shutil
import traceback
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests
from fastapi.testclient import TestClient

from backend import app as api, config
from backend.services import pixabay_stock as stock
from backend.services import video_providers as providers
from backend.services import visual_engine, voice_engine, video_compositor as compositor
from backend.services.media_tools import MediaError, executable, run_checked, validate_final
from backend.services.settings_store import update_env_keys


@pytest.fixture(autouse=True)
def clean_pixabay_state(monkeypatch, tmp_path):
    monkeypatch.setenv('PIXABAY_API_KEY', '')
    monkeypatch.setenv('PEXELS_API_KEY', '')
    monkeypatch.setenv('GEMINI_API_KEY', '')
    for name in ('PIXABAY_API_KEY', 'PEXELS_API_KEY', 'GEMINI_API_KEY'):
        monkeypatch.setattr(config, name, '')
    stock._LAST_REQUEST.clear()
    stock._COOLDOWN.clear()
    monkeypatch.setattr(stock, 'MIN_REQUEST_INTERVAL', 0)
    out, videos, music = tmp_path / 'output', tmp_path / 'videos', tmp_path / 'music'
    uploads = out / 'uploads'
    for path in (out, videos, music, uploads):
        path.mkdir(parents=True, exist_ok=True)
    for module in (api, providers, compositor, visual_engine, voice_engine):
        monkeypatch.setattr(module, 'OUTPUT_DIR', out, raising=False)
    for module in (api, providers):
        monkeypatch.setattr(module, 'UPLOADS_DIR', uploads)
        monkeypatch.setattr(module, 'VIDEOS_DIR', videos)
    monkeypatch.setattr(api, 'PROJECT_ROOT', tmp_path)
    monkeypatch.setattr(compositor, 'MUSIC_DIR', music)
    monkeypatch.setattr(api, 'RENDER_LOCK', asyncio.Semaphore(1))
    api.JOBS.clear()
    return SimpleNamespace(root=tmp_path, out=out, videos=videos, music=music, uploads=uploads)


@pytest.fixture(scope='module')
def media_files(tmp_path_factory):
    root = tmp_path_factory.mktemp('pixabay_test_media')
    ff = executable('ffmpeg')
    run_checked([ff, '-nostdin', '-y', '-v', 'error', '-f', 'lavfi', '-i',
                 'testsrc2=size=320x180:rate=24', '-t', '0.8', '-c:v', 'libx264',
                 '-threads', '1', '-pix_fmt', 'yuv420p', str(root / 'clip.mp4')])
    run_checked([ff, '-nostdin', '-y', '-v', 'error', '-f', 'lavfi', '-i',
                 'sine=frequency=440:sample_rate=48000', '-t', '0.8', str(root / 'voice.wav')])
    return root


def scene(number=1):
    return {'scene_number': number, 'search_keyword': 'laptop coding',
            'visual_prompt': 'A developer working on a laptop',
            'narration': '\u0c2e\u0c28\u0c02 \u0c15\u0c32\u0c3f\u0c38\u0c3f \u0c28\u0c47\u0c30\u0c4d\u0c1a\u0c41\u0c15\u0c41\u0c02\u0c26\u0c3e\u0c02',
            'roman_subtitles': 'Manam kalisi nerchukundam', 'duration_estimate_sec': 0.8}


def hit(number=101, width=1920, height=1080):
    return {'id': number, 'pageURL': f'https://pixabay.com/videos/id-{number}/',
            'user': 'Offline Test Creator', 'user_id': 200, 'duration': 5,
            'videos': {'large': {'width': 3840, 'height': 2160, 'size': 10000,
                                'url': f'https://cdn.pixabay.com/video/{number}-4k.mp4'},
                       'medium': {'width': width, 'height': height, 'size': 1000,
                                  'url': f'https://cdn.pixabay.com/video/{number}-hd.mp4'}}}


class Response:
    def __init__(self, payload=None, content=b'', status=200, headers=None):
        self.payload = payload
        self.content = content
        self.status_code = status
        self.headers = headers or {}
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def json(self):
        return self.payload
    def iter_content(self, size):
        yield self.content


def mock_http(monkeypatch, media_files, hits=None, status=200):
    calls = []
    hits = [hit()] if hits is None else hits
    def get(url, **kwargs):
        calls.append((url, kwargs))
        if url == stock.API_URL:
            return Response({'hits': hits, 'totalHits': len(hits)}, status=status)
        return Response(content=(media_files / 'clip.mp4').read_bytes())
    monkeypatch.setattr(stock.requests, 'get', get)
    return calls


def test_pixabay_missing_key_never_calls_network(monkeypatch, tmp_path):
    monkeypatch.setattr(stock.requests, 'get', lambda *a, **kw: pytest.fail('Network must not be called'))
    with pytest.raises(MediaError, match='key is missing'):
        stock.PixabayClient('', tmp_path).search('coding')


def test_key_resolution_runtime_and_request_override(monkeypatch):
    assert not providers.PixabayVideoProvider().is_available()
    monkeypatch.setenv('PIXABAY_API_KEY', 'runtime-test-key')
    assert providers.PixabayVideoProvider().is_available()
    assert providers.pixabay_key({'pixabay_api_key': 'request-test-key'}) == 'request-test-key'


def test_pixabay_hd_download_and_creator_provenance(clean_pixabay_state, media_files, monkeypatch):
    work = clean_pixabay_state
    calls = mock_http(monkeypatch, media_files)
    path = providers.PixabayVideoProvider().generate_clip(scene(), work.out / 'stock.mp4',
                                                        {'pixabay_api_key': 'test-key'})
    assert calls[0][0] == 'https://pixabay.com/api/videos/'
    assert calls[0][1]['params']['safesearch'] == 'true'
    assert 'orientation' not in calls[0][1]['params']  # Not a supported video API parameter.
    assert calls[1][0].endswith('101-hd.mp4')
    source = json.loads(path.with_suffix('.source.json').read_text())
    assert source['provider'] == 'pixabay' and source['video_id'] == 101
    assert source['creator']['name'] == 'Offline Test Creator'
    assert source['width'] == 320 and 'test-key' not in path.with_suffix('.source.json').read_text()


def test_portrait_result_preferred_among_query_hits(clean_pixabay_state, media_files, monkeypatch):
    calls = mock_http(monkeypatch, media_files, [hit(101), hit(102, 1080, 1920)])
    providers.PixabayVideoProvider().generate_clip(scene(), clean_pixabay_state.out / 'stock.mp4',
                                                 {'pixabay_api_key': 'test-key'})
    assert calls[1][0].endswith('102-hd.mp4')


def test_distinct_assets_preferred_across_scenes(clean_pixabay_state, media_files, monkeypatch):
    calls = mock_http(monkeypatch, media_files, [hit(101), hit(102)])
    used = set()
    for number in (1, 2):
        providers.PixabayVideoProvider().generate_clip(scene(number), clean_pixabay_state.out / f'{number}.mp4',
                                                     {'pixabay_api_key': 'test-key', 'used_clips': used})
    assert used == {'pixabay:101', 'pixabay:102'}
    assert sum(url == stock.API_URL for url, _ in calls) == 1
    assert [url for url, _ in calls if url != stock.API_URL][-1].endswith('102-hd.mp4')


def test_unavoidable_reuse_is_labelled(clean_pixabay_state, media_files, monkeypatch):
    mock_http(monkeypatch, media_files)
    path = providers.PixabayVideoProvider().generate_clip(scene(), clean_pixabay_state.out / 'stock.mp4',
        {'pixabay_api_key': 'test-key', 'used_clips': {'pixabay:101'}})
    assert json.loads(path.with_suffix('.source.json').read_text())['reused'] is True


def test_cache_success_for_24h_without_key_plaintext(tmp_path, media_files, monkeypatch):
    calls = mock_http(monkeypatch, media_files)
    client = stock.PixabayClient('do-not-print-this-test-secret', tmp_path / 'cache')
    first, cached = client.search('coding')
    second, cached_again = client.search('coding')
    assert not cached and cached_again and first == second and len(calls) == 1
    cache = next((tmp_path / 'cache').glob('*.json'))
    assert 'do-not-print-this-test-secret' not in cache.read_text() + cache.name
    data = json.loads(cache.read_text())
    data['saved_at'] -= stock.CACHE_SECONDS + 1
    cache.write_text(json.dumps(data))
    assert client.search('coding')[1] is False
    assert len(calls) == 2


def test_changed_key_does_not_reuse_old_auth_cache(tmp_path, media_files, monkeypatch):
    calls = mock_http(monkeypatch, media_files)
    for key in ('first-test-key', 'second-test-key'):
        assert not stock.PixabayClient(key, tmp_path / 'cache').search('coding')[1]
    assert len(calls) == 2


def test_empty_results_are_cached_without_random_fallback(clean_pixabay_state, media_files, monkeypatch):
    calls = mock_http(monkeypatch, media_files, [])
    client = stock.PixabayClient('test-key', clean_pixabay_state.out / 'cache')
    for _ in range(2):
        with pytest.raises(MediaError, match='No usable Pixabay video matched'):
            client.fetch_scene(scene(), clean_pixabay_state.out / 'empty.mp4', set())
    assert len(calls) == 1
    assert not (clean_pixabay_state.out / 'empty.mp4').exists()


@pytest.mark.parametrize('status', [400, 401, 403, 429, 500])
def test_http_errors_are_actionable_and_secret_free(tmp_path, media_files, monkeypatch, status):
    mock_http(monkeypatch, media_files, status=status)
    with pytest.raises(MediaError) as error:
        stock.PixabayClient('secret-test-key', tmp_path / 'cache').search('coding')
    assert 'secret-test-key' not in str(error.value)
    assert 'rate limit' in str(error.value) if status == 429 else str(status) in str(error.value)


def test_rate_limit_does_not_retry_on_every_scene(tmp_path, monkeypatch):
    calls = []
    def get(*args, **kwargs):
        calls.append(args)
        return Response(status=429, headers={'Retry-After': '60'})
    monkeypatch.setattr(stock.requests, 'get', get)
    client = stock.PixabayClient('test-key', tmp_path / 'cache')
    for query in ('coding', 'robot'):
        with pytest.raises(MediaError, match='rate limit'):
            client.search(query)
    assert len(calls) == 1


def test_requests_error_does_not_leak_key_in_traceback(tmp_path, monkeypatch):
    def bad_request(*a, **kw):
        raise requests.ConnectionError('https://pixabay.com/api/videos/?key=PRIVATE-TEST-KEY')
    monkeypatch.setattr(stock.requests, 'get', bad_request)
    private_key = 'PRIVATE-TEST-KEY'
    client = stock.PixabayClient(private_key, tmp_path / 'cache')
    try:
        client.search('coding')
    except MediaError:
        diagnostic = traceback.format_exc()
    assert 'PRIVATE-TEST-KEY' not in diagnostic
    assert 'Cannot connect to Pixabay' in diagnostic


@pytest.mark.parametrize('payload', [[], {'hits': 'wrong'}, {'hits': None}])
def test_invalid_api_json_is_not_accepted(tmp_path, monkeypatch, payload):
    monkeypatch.setattr(stock.requests, 'get', lambda *a, **kw: Response(payload))
    with pytest.raises(MediaError, match='unexpected response'):
        stock.PixabayClient('test-key', tmp_path).search('coding')


def test_malformed_renditions_are_skipped(clean_pixabay_state, media_files, monkeypatch):
    bad = hit()
    bad['videos'] = ['not-a-dictionary']
    mock_http(monkeypatch, media_files, [bad])
    with pytest.raises(MediaError, match='No usable Pixabay'):
        providers.PixabayVideoProvider().generate_clip(scene(), clean_pixabay_state.out / 'a.mp4',
                                                      {'pixabay_api_key': 'test-key'})


def test_oversized_stream_removed(tmp_path, monkeypatch):
    monkeypatch.setattr(stock, 'MAX_MEDIA_BYTES', 10)
    monkeypatch.setattr(stock.requests, 'get', lambda *a, **kw: Response(content=b'x' * 20))
    with pytest.raises(MediaError, match='250 MB'):
        stock.PixabayClient('key', tmp_path)._download('https://cdn.pixabay.com/video/test.mp4', tmp_path / 'a.mp4')
    assert not list(tmp_path.glob('*.download')) and not (tmp_path / 'a.mp4').exists()


def test_corrupt_video_does_not_mark_candidate_used(clean_pixabay_state, monkeypatch):
    def get(url, **kwargs):
        return Response({'hits': [hit()], 'totalHits': 1}) if url == stock.API_URL else Response(content=b'not video' * 500)
    monkeypatch.setattr(stock.requests, 'get', get)
    used = set()
    with pytest.raises(MediaError, match='No Pixabay candidate passed'):
        providers.PixabayVideoProvider().generate_clip(scene(), clean_pixabay_state.out / 'a.mp4',
                                                      {'pixabay_api_key': 'test-key', 'used_clips': used})
    assert not used and not list(clean_pixabay_state.out.glob('*.download'))


def test_redirect_cannot_access_localhost(tmp_path, monkeypatch):
    calls = []
    def get(url, **kwargs):
        calls.append(url)
        return Response(status=302, headers={'Location': 'http://127.0.0.1/private'})
    monkeypatch.setattr(stock.requests, 'get', get)
    with pytest.raises(MediaError, match='unsupported host'):
        stock.PixabayClient('key', tmp_path)._download('https://cdn.pixabay.com/video/a.mp4', tmp_path / 'a.mp4')
    assert len(calls) == 1


def test_unsafe_media_url_never_downloaded(clean_pixabay_state, media_files, monkeypatch):
    bad = hit()
    for variant in bad['videos'].values():
        variant['url'] = 'http://localhost/secret.mp4'
    calls = mock_http(monkeypatch, media_files, [bad])
    with pytest.raises(MediaError, match='No usable Pixabay'):
        providers.PixabayVideoProvider().generate_clip(scene(), clean_pixabay_state.out / 'a.mp4',
                                                      {'pixabay_api_key': 'test-key'})
    assert len(calls) == 1


def test_manual_upload_still_overrides_pixabay(clean_pixabay_state, media_files, monkeypatch):
    target = clean_pixabay_state.uploads / 'mine.mp4'
    shutil.copy2(media_files / 'clip.mp4', target)
    monkeypatch.setattr(stock.requests, 'get', lambda *a, **kw: pytest.fail('Upload must not contact stock providers'))
    path, name = providers.ROUTER.resolve_scene_clip(scene(), clean_pixabay_state.out / 'out.mp4', 0,
        preferred_provider='pixabay', custom_clips={'scene_1': target.name}, pixabay_api_key='test-key')
    assert path == target and name == 'User-selected video'


def test_auto_router_uses_pixabay_and_records_source(clean_pixabay_state, media_files, monkeypatch):
    mock_http(monkeypatch, media_files)
    trace = []
    path, name = providers.ROUTER.resolve_scene_clip(scene(), clean_pixabay_state.out / 'out.mp4', 0,
        pixabay_api_key='test-key', trace=trace)
    assert name == 'Pixabay stock video' and path.is_file()
    assert trace[-1]['provider'] == 'pixabay' and trace[-1]['source_url'].startswith('https://pixabay.com/')
    assert trace[0]['provider'] == 'pexels' and trace[0]['status'] == 'failed'


def test_explicit_pixabay_failure_does_not_silently_change_provider(clean_pixabay_state, media_files, monkeypatch):
    shutil.copy2(media_files / 'clip.mp4', clean_pixabay_state.videos / 'laptop_coding.mp4')
    mock_http(monkeypatch, media_files, [])
    with pytest.raises(MediaError, match='no usable footage'):
        providers.ROUTER.resolve_scene_clip(scene(), clean_pixabay_state.out / 'out.mp4', 0,
            preferred_provider='pixabay', pixabay_api_key='test-key')


def test_auto_can_fall_back_to_matched_local_footage(clean_pixabay_state, media_files, monkeypatch):
    target = clean_pixabay_state.videos / 'laptop_coding.mp4'
    shutil.copy2(media_files / 'clip.mp4', target)
    mock_http(monkeypatch, media_files, status=403)
    path, name = providers.ROUTER.resolve_scene_clip(scene(), clean_pixabay_state.out / 'out.mp4', 0,
        pixabay_api_key='test-key')
    assert path == target and name == 'Matched local library'


def test_preflight_accepts_pixabay_key_but_does_not_claim_online_validation(clean_pixabay_state):
    payload = {'storyboard': {'scenes': [scene()]}, 'pixabay_api_key': 'test-key',
               'scene_providers': {'scene_1': 'pixabay'}}
    with TestClient(api.app) as client:
        result = client.post('/api/preflight', json=payload).json()
    assert result['ready'] and 'during rendering' in result['warnings'][0]


def test_preflight_rejects_missing_pixabay_key(clean_pixabay_state):
    payload = {'storyboard': {'scenes': [scene()]}, 'scene_providers': {'scene_1': 'pixabay'}}
    with TestClient(api.app) as client:
        result = client.post('/api/preflight', json=payload).json()
    assert not result['ready'] and 'Pixabay key is missing' in result['errors'][0]


def test_settings_save_keeps_ffmpeg_and_other_credentials(clean_pixabay_state):
    path = clean_pixabay_state.root / '.env'
    original = (b'# User configuration\r\nFFMPEG_EXE=C:\\tools\\ffmpeg.exe\r\n'
                b'FFPROBE_EXE=C:\\tools\\ffprobe.exe\r\nGEMINI_API_KEY=existing-gemini\r\n'
                b'PEXELS_API_KEY=existing-pexels\r\nPIXABAY_API_KEY=\r\nPIXABAY_API_KEY=old-test-key\r\n')
    path.write_bytes(original)
    with TestClient(api.app) as client:
        response = client.post('/api/settings', json={'pixabay_api_key': 'new-test-pixabay'})
        assert response.status_code == 200
        settings = client.get('/api/settings').json()
        assert settings['has_pixabay_key'] and 'new-test-pixabay' not in json.dumps(settings)
        provider_rows = client.get('/api/video-providers').json()
        assert next(row for row in provider_rows if row['id'] == 'pixabay')['is_available']
    after = path.read_bytes()
    assert after.count(b'PIXABAY_API_KEY=') == 1
    for line in original.splitlines(keepends=True):
        if not line.startswith(b'PIXABAY'):
            assert line in after


def test_settings_key_append_handles_missing_final_newline(tmp_path):
    path = tmp_path / '.env'
    original = b'\xef\xbb\xbfFFMPEG_EXE=C:/ffmpeg.exe\r\nFFPROBE_EXE=C:/ffprobe.exe'
    path.write_bytes(original)
    update_env_keys(path, {'PIXABAY_API_KEY': 'test-key'})
    assert path.read_bytes() == original + b'\r\nPIXABAY_API_KEY=test-key\r\n'


def test_empty_settings_submission_does_not_erase_config(clean_pixabay_state):
    path = clean_pixabay_state.root / '.env'
    original = b'FFMPEG_EXE=C:\\tools\\ffmpeg.exe\nPIXABAY_API_KEY=previous-key'
    path.write_bytes(original)
    with TestClient(api.app) as client:
        assert client.post('/api/settings', json={}).status_code == 200
    assert path.read_bytes() == original


def test_settings_newline_injection_rejected_without_mutation(clean_pixabay_state):
    path = clean_pixabay_state.root / '.env'
    path.write_text('FFMPEG_EXE=keep-me\n')
    with TestClient(api.app) as client:
        response = client.post('/api/settings', json={'pixabay_api_key': 'bad\nFFMPEG_EXE=changed'})
    assert response.status_code == 400 and path.read_text() == 'FFMPEG_EXE=keep-me\n'
    assert not providers.pixabay_key()


def test_test_key_endpoint_does_not_save_a_typed_key(clean_pixabay_state, media_files, monkeypatch):
    calls = mock_http(monkeypatch, media_files)
    with TestClient(api.app) as client:
        response = client.post('/api/test-pixabay-key', json={'pixabay_api_key': 'unsaved-test-key'})
        assert response.json()['valid']
        assert not client.get('/api/settings').json()['has_pixabay_key']
    assert not (clean_pixabay_state.root / '.env').exists()
    assert calls[0][1]['params']['per_page'] == 3


def test_mixed_upload_pixabay_pipeline_keeps_telugu_roman_music_and_1080p(clean_pixabay_state, media_files, monkeypatch):
    work = clean_pixabay_state
    mock_http(monkeypatch, media_files)
    uploaded = work.uploads / 'owned.mp4'
    shutil.copy2(media_files / 'clip.mp4', uploaded)
    # Use real sound data as narration test input, not live Telugu synthesis.
    seen_voice_ids = []
    async def voices(scenes, voice_id, job_id):
        seen_voice_ids.append(voice_id)
        return [{'audio_path': str(media_files / 'voice.wav'), 'duration': 0.8, 'words': []} for s in scenes]
    monkeypatch.setattr(api, '_generate_scene_voices', voices)
    run_checked([executable('ffmpeg'), '-nostdin', '-y', '-v', 'error', '-i', str(media_files / 'voice.wav'),
                 str(work.music / 'test_music.mp3')])
    payload = {'storyboard': {'scenes': [scene(1), scene(2), scene(3)]},
               'voice_id': 'te-IN-MohanNeural', 'subtitle_format': 'roman', 'music_track': 'test_music',
               'pixabay_api_key': 'request-test-key',
               'custom_clips': {'scene_1': uploaded.name, 'scene_3': uploaded.name},
               'scene_providers': {'scene_2': 'pixabay'}}
    with TestClient(api.app) as client:
        response = client.post('/api/render-video', json=payload)
        assert response.status_code == 200, response.text
        job_id = response.json()['job_id']
        job = client.get(f'/api/job/{job_id}').json()
    assert job['status'] == 'COMPLETED', job
    assert seen_voice_ids == ['te-IN-MohanNeural']
    selected = [row for row in job['visual_report'] if row['status'] == 'selected']
    assert [row['provider'] for row in selected] == ['upload', 'pixabay', 'upload']
    output = work.out / f'{job_id}_final.mp4'
    info = validate_final(output, 2.4, full_decode=True)
    assert (info['video']['width'], info['video']['height']) == (1080, 1920)
    assert info['video']['r_frame_rate'] == '30/1' and info['audio']['sample_rate'] == '48000'
    subtitles = '\n'.join(p.read_text() for p in (work.out / 'jobs' / job_id).glob('*.ass'))
    assert 'MANAM' in subtitles.upper()


def test_failed_job_retains_provider_attempt_report(clean_pixabay_state, media_files, monkeypatch):
    mock_http(monkeypatch, media_files, [])
    payload = {'storyboard': {'scenes': [scene()]}, 'pixabay_api_key': 'request-test-key',
               'scene_providers': {'scene_1': 'pixabay'}}
    with TestClient(api.app) as client:
        response = client.post('/api/render-video', json=payload)
        job = client.get('/api/job/' + response.json()['job_id']).json()
    assert job['status'] == 'FAILED' and job['video_url'] is None
    assert job['visual_report'][0]['provider'] == 'pixabay'
    assert 'request-test-key' not in json.dumps(job)
