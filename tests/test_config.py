# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""Tests for esp_pylib.config — ToolConfig search, parse, cache."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from esp_pylib import config as config_mod
from esp_pylib.config import ToolConfig
from esp_pylib.errors import ConfigError

if TYPE_CHECKING:
    from pathlib import Path


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')


# ---------------------------------------------------------------------------
# Search-order tests (using the explicit ``search_dirs`` override so we
# don't depend on the user's real cwd / home / config directory).
# ---------------------------------------------------------------------------


class TestFindSearchOrder:
    def test_returns_none_when_no_file_exists(self, tmp_path):
        cfg = ToolConfig('mytool', ['mytool.cfg'], search_dirs=[tmp_path])
        assert cfg.find() is None

    def test_finds_file_in_first_dir(self, tmp_path):
        a = tmp_path / 'a'
        b = tmp_path / 'b'
        _write(a / 'mytool.cfg', '[mytool]\nkey=A\n')
        _write(b / 'mytool.cfg', '[mytool]\nkey=B\n')
        cfg = ToolConfig('mytool', ['mytool.cfg'], search_dirs=[a, b])
        assert cfg.find() == a / 'mytool.cfg'

    def test_falls_through_to_second_dir(self, tmp_path):
        a = tmp_path / 'a'
        b = tmp_path / 'b'
        a.mkdir()  # exists but no config inside
        _write(b / 'mytool.cfg', '[mytool]\nkey=B\n')
        cfg = ToolConfig('mytool', ['mytool.cfg'], search_dirs=[a, b])
        assert cfg.find() == b / 'mytool.cfg'

    def test_filename_priority_within_dir(self, tmp_path):
        # When multiple candidate filenames exist in the same dir,
        # the first listed name wins.
        _write(tmp_path / 'mytool.cfg', '[mytool]\nkey=X\n')
        _write(tmp_path / 'setup.cfg', '[mytool]\nkey=Y\n')
        cfg = ToolConfig('mytool', ['mytool.cfg', 'setup.cfg'], search_dirs=[tmp_path])
        assert cfg.find() == tmp_path / 'mytool.cfg'

    def test_skips_files_without_section(self, tmp_path):
        # esptool's real-world case: setup.cfg often exists for unrelated
        # tooling. We must not "claim" it just because it's a candidate name.
        _write(tmp_path / 'setup.cfg', '[flake8]\nmax-line-length=99\n')
        next_dir = tmp_path / 'next'
        _write(next_dir / 'setup.cfg', '[mytool]\nkey=Z\n')
        cfg = ToolConfig('mytool', ['setup.cfg'], search_dirs=[tmp_path, next_dir])
        assert cfg.find() == next_dir / 'setup.cfg'

    def test_skips_unparseable_file(self, tmp_path):
        # Garbage bytes that can't be decoded as UTF-8 are silently skipped.
        bad = tmp_path / 'mytool.cfg'
        bad.write_bytes(b'\xff\xfe\xff\xfe not valid utf-8 \xff')
        good = tmp_path / 'next' / 'mytool.cfg'
        _write(good, '[mytool]\nkey=Z\n')
        cfg = ToolConfig('mytool', ['mytool.cfg'], search_dirs=[tmp_path, tmp_path / 'next'])
        assert cfg.find() == good

    def test_skips_invalid_ini_syntax(self, tmp_path):
        # configparser raises on malformed INI; we treat that the same as
        # "no match" rather than propagating and breaking the search.
        _write(tmp_path / 'mytool.cfg', 'this is { not [ini\n=??\n')
        good = tmp_path / 'next' / 'mytool.cfg'
        _write(good, '[mytool]\nkey=Z\n')
        cfg = ToolConfig('mytool', ['mytool.cfg'], search_dirs=[tmp_path, tmp_path / 'next'])
        assert cfg.find() == good


# ---------------------------------------------------------------------------
# Env var override
# ---------------------------------------------------------------------------


class TestEnvVarOverride:
    def test_uses_env_var_path(self, tmp_path, monkeypatch):
        target = tmp_path / 'custom.cfg'
        _write(target, '[mytool]\nkey=ENV\n')
        monkeypatch.setenv('MYTOOL_CFGFILE', str(target))
        cfg = ToolConfig(
            'mytool',
            ['mytool.cfg'],
            env_var='MYTOOL_CFGFILE',
            search_dirs=[tmp_path / 'never_searched'],
        )
        assert cfg.find() == target

    def test_env_var_takes_precedence_over_search_dirs(self, tmp_path, monkeypatch):
        env_path = tmp_path / 'env.cfg'
        search_path = tmp_path / 'search' / 'mytool.cfg'
        _write(env_path, '[mytool]\nkey=ENV\n')
        _write(search_path, '[mytool]\nkey=SEARCH\n')
        monkeypatch.setenv('MYTOOL_CFGFILE', str(env_path))
        cfg = ToolConfig(
            'mytool',
            ['mytool.cfg'],
            env_var='MYTOOL_CFGFILE',
            search_dirs=[tmp_path / 'search'],
        )
        assert cfg.find() == env_path
        assert cfg.get('key') == 'ENV'

    def test_empty_env_var_falls_through_to_search(self, tmp_path, monkeypatch):
        # An empty string from the env var must be treated as "not set",
        # not as the cwd or some other accidental path.
        search_path = tmp_path / 'mytool.cfg'
        _write(search_path, '[mytool]\nkey=SEARCH\n')
        monkeypatch.setenv('MYTOOL_CFGFILE', '')
        cfg = ToolConfig(
            'mytool',
            ['mytool.cfg'],
            env_var='MYTOOL_CFGFILE',
            search_dirs=[tmp_path],
        )
        assert cfg.find() == search_path

    def test_env_var_missing_file_raises(self, tmp_path, monkeypatch):
        monkeypatch.setenv('MYTOOL_CFGFILE', str(tmp_path / 'does_not_exist.cfg'))
        cfg = ToolConfig(
            'mytool',
            ['mytool.cfg'],
            env_var='MYTOOL_CFGFILE',
            search_dirs=[tmp_path],
        )
        with pytest.raises(ConfigError, match='not found'):
            cfg.find()

    def test_env_var_path_without_section_raises(self, tmp_path, monkeypatch):
        # When the user explicitly points at a file, missing the tool's
        # section is a hard error (not a silent fall-through).
        bad = tmp_path / 'wrong.cfg'
        _write(bad, '[someone_else]\nkey=val\n')
        monkeypatch.setenv('MYTOOL_CFGFILE', str(bad))
        cfg = ToolConfig(
            'mytool',
            ['mytool.cfg'],
            env_var='MYTOOL_CFGFILE',
            search_dirs=[tmp_path],
        )
        with pytest.raises(ConfigError, match=r'has no \[mytool\] section'):
            cfg.find()

    def test_no_env_var_configured(self, tmp_path):
        # When env_var=None, even setting random env vars has no effect.
        path = tmp_path / 'mytool.cfg'
        _write(path, '[mytool]\nkey=X\n')
        cfg = ToolConfig('mytool', ['mytool.cfg'], env_var=None, search_dirs=[tmp_path])
        assert cfg.find() == path


# ---------------------------------------------------------------------------
# load() — tuple return shape and parsing behavior
# ---------------------------------------------------------------------------


class TestLoad:
    def test_load_returns_parser_and_path(self, tmp_path):
        path = tmp_path / 'mytool.cfg'
        _write(path, '[mytool]\nkey=value\n')
        cfg = ToolConfig('mytool', ['mytool.cfg'], search_dirs=[tmp_path])
        parser, returned = cfg.load()
        assert returned == path
        assert parser['mytool']['key'] == 'value'

    def test_load_no_file_returns_empty_parser_with_section(self, tmp_path):
        # An empty section is pre-created so callers can write
        # parser['mytool'].get(...) without first checking has_section.
        cfg = ToolConfig('mytool', ['mytool.cfg'], search_dirs=[tmp_path])
        parser, returned = cfg.load()
        assert returned is None
        assert parser.has_section('mytool')
        assert dict(parser['mytool']) == {}

    def test_load_preserves_all_options(self, tmp_path):
        path = tmp_path / 'mytool.cfg'
        _write(path, '[mytool]\ntimeout = 10\nbaud = 921600\nname = foo\n')
        cfg = ToolConfig('mytool', ['mytool.cfg'], search_dirs=[tmp_path])
        parser, _ = cfg.load()
        assert parser['mytool']['timeout'] == '10'
        assert parser['mytool']['baud'] == '921600'
        assert parser['mytool']['name'] == 'foo'

    def test_load_unrelated_sections_preserved(self, tmp_path):
        # Tools may want to read sibling sections that are also in the file.
        path = tmp_path / 'mytool.cfg'
        _write(path, '[mytool]\nkey=A\n[other]\nfoo=bar\n')
        cfg = ToolConfig('mytool', ['mytool.cfg'], search_dirs=[tmp_path])
        parser, _ = cfg.load()
        assert parser['other']['foo'] == 'bar'


# ---------------------------------------------------------------------------
# get() — convenience accessor
# ---------------------------------------------------------------------------


class TestGet:
    def test_get_returns_value(self, tmp_path):
        _write(tmp_path / 'mytool.cfg', '[mytool]\ntimeout=99\n')
        cfg = ToolConfig('mytool', ['mytool.cfg'], search_dirs=[tmp_path])
        assert cfg.get('timeout') == '99'

    def test_get_returns_fallback_when_key_missing(self, tmp_path):
        _write(tmp_path / 'mytool.cfg', '[mytool]\n')
        cfg = ToolConfig('mytool', ['mytool.cfg'], search_dirs=[tmp_path])
        assert cfg.get('missing', fallback='default') == 'default'

    def test_get_returns_fallback_when_no_file(self, tmp_path):
        cfg = ToolConfig('mytool', ['mytool.cfg'], search_dirs=[tmp_path])
        assert cfg.get('missing', fallback='default') == 'default'

    def test_get_returns_none_by_default(self, tmp_path):
        cfg = ToolConfig('mytool', ['mytool.cfg'], search_dirs=[tmp_path])
        assert cfg.get('missing') is None

    def test_get_returns_literal_percent_value(self, tmp_path):
        # Regression: ``ConfigParser`` defaults to ``%``-style interpolation,
        # which would reject a perfectly valid value like ``100%``. ``find()``
        # uses ``RawConfigParser``, so without ``interpolation=None`` in
        # ``load()`` the same file would pass discovery and then raise
        # ``InterpolationSyntaxError`` on the first ``get()``.
        _write(tmp_path / 'mytool.cfg', '[mytool]\nprogress=100%\n')
        cfg = ToolConfig('mytool', ['mytool.cfg'], search_dirs=[tmp_path])
        assert cfg.get('progress') == '100%'

    def test_load_preserves_literal_percent_value(self, tmp_path):
        _write(tmp_path / 'mytool.cfg', '[mytool]\nratio=50%\n')
        cfg = ToolConfig('mytool', ['mytool.cfg'], search_dirs=[tmp_path])
        parser, _ = cfg.load()
        assert parser['mytool']['ratio'] == '50%'


# ---------------------------------------------------------------------------
# Caching
# ---------------------------------------------------------------------------


class TestCaching:
    def test_find_cached_after_first_call(self, tmp_path):
        path = tmp_path / 'mytool.cfg'
        _write(path, '[mytool]\nkey=X\n')
        cfg = ToolConfig('mytool', ['mytool.cfg'], search_dirs=[tmp_path])
        assert cfg.find() == path
        # Delete the file; cached find() must still return the original path.
        path.unlink()
        assert cfg.find() == path

    def test_find_caches_negative_result(self, tmp_path):
        # The first find() returns None (no file); subsequent find() must
        # also return None even if a file appears, until reload() is called.
        cfg = ToolConfig('mytool', ['mytool.cfg'], search_dirs=[tmp_path])
        assert cfg.find() is None
        _write(tmp_path / 'mytool.cfg', '[mytool]\nkey=X\n')
        assert cfg.find() is None  # still cached

    def test_load_cached_after_first_call(self, tmp_path):
        path = tmp_path / 'mytool.cfg'
        _write(path, '[mytool]\nkey=X\n')
        cfg = ToolConfig('mytool', ['mytool.cfg'], search_dirs=[tmp_path])
        parser1, _ = cfg.load()
        # Mutate the file on disk; cached parser must NOT see the change.
        path.write_text('[mytool]\nkey=Y\n', encoding='utf-8')
        parser2, _ = cfg.load()
        assert parser1 is parser2
        assert parser2['mytool']['key'] == 'X'

    def test_reload_drops_cache(self, tmp_path):
        path = tmp_path / 'mytool.cfg'
        _write(path, '[mytool]\nkey=X\n')
        cfg = ToolConfig('mytool', ['mytool.cfg'], search_dirs=[tmp_path])
        assert cfg.get('key') == 'X'
        path.write_text('[mytool]\nkey=Y\n', encoding='utf-8')
        cfg.reload()
        assert cfg.get('key') == 'Y'

    def test_repeated_get_does_not_re_read(self, tmp_path):
        # Sanity: many get() calls only trigger one disk read of the file.
        # We assert this by patching ConfigParser.read and counting calls.
        path = tmp_path / 'mytool.cfg'
        _write(path, '[mytool]\nkey=X\n')
        cfg = ToolConfig('mytool', ['mytool.cfg'], search_dirs=[tmp_path])
        with patch.object(config_mod.configparser.ConfigParser, 'read', autospec=True) as mock_read:
            # Real parsing still has to populate the section; do it manually.
            def _populate(self, filenames, encoding=None):
                self[cfg.section_name] = {'key': 'X'}
                return [str(path)]

            mock_read.side_effect = _populate
            for _ in range(5):
                assert cfg.get('key') == 'X'
        assert mock_read.call_count == 1


# ---------------------------------------------------------------------------
# Default search dirs (platform-aware)
# ---------------------------------------------------------------------------


class TestDefaultSearchDirs:
    def test_posix_search_dirs(self, tmp_path, monkeypatch):
        # We avoid asserting on ``Path.cwd()`` because patching ``os.name`` on
        # Python 3.13+ makes ``Path.cwd()`` instantiate the wrong subclass and
        # raise ``UnsupportedOperation``. The cwd element is exercised end-to-end
        # in `TestRealisticConfigurations`; here we focus on the
        # platform-specific user-config dir, which is the actual variable bit.
        monkeypatch.setattr(config_mod.os, 'name', 'posix')
        monkeypatch.setattr(config_mod.Path, 'home', staticmethod(lambda: tmp_path))
        cfg = ToolConfig('mytool', ['mytool.cfg'])
        with patch.object(config_mod.Path, 'cwd', staticmethod(lambda: tmp_path)):
            dirs = cfg._default_search_dirs()
        assert dirs == [
            tmp_path,  # cwd (mocked)
            tmp_path / '.config' / 'mytool',
            tmp_path,  # home
        ]

    def test_windows_search_dirs(self, tmp_path, monkeypatch):
        # Same caveat as above: ``Path.cwd()`` cannot run on a non-Windows host
        # while ``os.name == 'nt'`` is in effect, so we mock it.
        monkeypatch.setattr(config_mod.os, 'name', 'nt')
        monkeypatch.setattr(config_mod.Path, 'home', staticmethod(lambda: tmp_path))
        cfg = ToolConfig('mytool', ['mytool.cfg'])
        with patch.object(config_mod.Path, 'cwd', staticmethod(lambda: tmp_path)):
            dirs = cfg._default_search_dirs()
        assert dirs == [
            tmp_path,  # cwd (mocked)
            tmp_path / 'AppData' / 'Local' / 'mytool',
            tmp_path,  # home
        ]

    def test_cwd_is_first_in_default_search(self, tmp_path, monkeypatch):
        # Real-world use: user runs the tool from a project dir that has
        # its own config; that config must win over the user-config dir.
        project = tmp_path / 'project'
        config_dir = tmp_path / '.config' / 'mytool'
        _write(project / 'mytool.cfg', '[mytool]\nkey=PROJECT\n')
        _write(config_dir / 'mytool.cfg', '[mytool]\nkey=USER\n')

        monkeypatch.setattr(config_mod.os, 'name', 'posix')
        monkeypatch.setattr(config_mod.Path, 'home', staticmethod(lambda: tmp_path))
        monkeypatch.chdir(project)

        cfg = ToolConfig('mytool', ['mytool.cfg'])
        assert cfg.get('key') == 'PROJECT'

    def test_user_config_dir_used_when_cwd_has_no_config(self, tmp_path, monkeypatch):
        config_dir = tmp_path / '.config' / 'mytool'
        _write(config_dir / 'mytool.cfg', '[mytool]\nkey=USER\n')

        monkeypatch.setattr(config_mod.os, 'name', 'posix')
        monkeypatch.setattr(config_mod.Path, 'home', staticmethod(lambda: tmp_path))
        # Fresh empty project dir to guarantee cwd has no config file.
        empty = tmp_path / 'empty'
        empty.mkdir()
        monkeypatch.chdir(empty)

        cfg = ToolConfig('mytool', ['mytool.cfg'])
        assert cfg.get('key') == 'USER'


# ---------------------------------------------------------------------------
# Integration: realistic multi-filename and single-filename configurations
# ---------------------------------------------------------------------------


class TestRealisticConfigurations:
    def test_multi_filename_picks_first_with_section(self, tmp_path):
        # When several candidate filenames are searched (e.g. a tool-specific
        # ``<tool>.cfg`` plus shared ``setup.cfg`` / ``tox.ini``), only the
        # one carrying the tool's section should be selected.
        _write(tmp_path / 'setup.cfg', '[flake8]\nmax-line-length=99\n')
        _write(tmp_path / 'tox.ini', '[esptool]\ntimeout=30\n')
        cfg = ToolConfig(
            'esptool',
            ['esptool.cfg', 'setup.cfg', 'tox.ini'],
            search_dirs=[tmp_path],
        )
        path = cfg.find()
        assert path == tmp_path / 'tox.ini'
        assert cfg.get('timeout') == '30'

    def test_single_filename_with_env_var_override(self, tmp_path):
        # The minimal setup: one candidate filename plus an override env var.
        _write(tmp_path / 'idf_monitor.cfg', '[esp-idf-monitor]\ntimeout=10\n')
        cfg = ToolConfig(
            'esp-idf-monitor',
            ['idf_monitor.cfg'],
            env_var='ESP_IDF_MONITOR_CFGFILE',
            search_dirs=[tmp_path],
        )
        parser, path = cfg.load()
        assert path == tmp_path / 'idf_monitor.cfg'
        assert parser['esp-idf-monitor']['timeout'] == '10'


# ---------------------------------------------------------------------------
# Permissive env-var fallback (opt-in)
# ---------------------------------------------------------------------------


class TestPermissiveEnvVar:
    def test_missing_env_var_file_falls_back_to_search(self, tmp_path, monkeypatch):
        # With permissive_env_var=True, a missing env-var target must not
        # raise; the loader falls back to the standard search path.
        search_path = tmp_path / 'mytool.cfg'
        _write(search_path, '[mytool]\nkey=SEARCH\n')
        monkeypatch.setenv('MYTOOL_CFGFILE', str(tmp_path / 'does_not_exist.cfg'))
        cfg = ToolConfig(
            'mytool',
            ['mytool.cfg'],
            env_var='MYTOOL_CFGFILE',
            search_dirs=[tmp_path],
            permissive_env_var=True,
        )
        assert cfg.find() == search_path

    def test_env_var_without_section_falls_back_to_search(self, tmp_path, monkeypatch):
        bad = tmp_path / 'wrong.cfg'
        _write(bad, '[someone_else]\nkey=val\n')
        search_path = tmp_path / 'search' / 'mytool.cfg'
        _write(search_path, '[mytool]\nkey=SEARCH\n')
        monkeypatch.setenv('MYTOOL_CFGFILE', str(bad))
        cfg = ToolConfig(
            'mytool',
            ['mytool.cfg'],
            env_var='MYTOOL_CFGFILE',
            search_dirs=[tmp_path / 'search'],
            permissive_env_var=True,
        )
        assert cfg.find() == search_path

    def test_permissive_with_no_search_match_returns_none(self, tmp_path, monkeypatch):
        # Permissive fallback + nothing in the search dirs → None, not raise.
        monkeypatch.setenv('MYTOOL_CFGFILE', str(tmp_path / 'does_not_exist.cfg'))
        cfg = ToolConfig(
            'mytool',
            ['mytool.cfg'],
            env_var='MYTOOL_CFGFILE',
            search_dirs=[tmp_path],
            permissive_env_var=True,
        )
        assert cfg.find() is None

    def test_permissive_still_uses_valid_env_var(self, tmp_path, monkeypatch):
        # When the env-var target is valid, permissive mode must not change
        # the precedence — env var still wins over the search path.
        env_path = tmp_path / 'env.cfg'
        _write(env_path, '[mytool]\nkey=ENV\n')
        search_path = tmp_path / 'search' / 'mytool.cfg'
        _write(search_path, '[mytool]\nkey=SEARCH\n')
        monkeypatch.setenv('MYTOOL_CFGFILE', str(env_path))
        cfg = ToolConfig(
            'mytool',
            ['mytool.cfg'],
            env_var='MYTOOL_CFGFILE',
            search_dirs=[tmp_path / 'search'],
            permissive_env_var=True,
        )
        assert cfg.find() == env_path
        assert cfg.get('key') == 'ENV'

    def test_default_is_strict(self, tmp_path, monkeypatch):
        # Sanity: without permissive_env_var=True, behavior is unchanged
        # (a missing env-var target raises). Mirrors TestEnvVarOverride
        # but kept here so the contrast with the permissive cases above
        # is obvious in the file.
        monkeypatch.setenv('MYTOOL_CFGFILE', str(tmp_path / 'missing.cfg'))
        cfg = ToolConfig(
            'mytool',
            ['mytool.cfg'],
            env_var='MYTOOL_CFGFILE',
            search_dirs=[tmp_path],
        )
        with pytest.raises(ConfigError, match='not found'):
            cfg.find()


# ---------------------------------------------------------------------------
# Verbose logging hooks: warn_fn, info_fn, valid_options
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# verbose=True flag — gates emission through ``esp_pylib.logger.log``
# ---------------------------------------------------------------------------


@pytest.fixture
def capture_log():
    """Install a capture logger as ``EspLog.instance`` for the test, then
    restore the previous singleton on teardown. Avoids cross-test pollution
    when other tests in the suite construct a real ``EspLog``.
    """
    from esp_pylib.logger import EspLog
    from esp_pylib.logger import EspLogBase

    # Defined inside the fixture so that importing this test module — and
    # therefore importing ``esp_pylib.config`` for it — doesn't drag in
    # ``esp_pylib.logger`` (and rich) at module load time. That keeps
    # ``TestNoOptionalDepsRequired`` honest: only verbose-flag tests that
    # actually exercise the logger pull in this dependency.
    class _CaptureLogger(EspLogBase):
        def __init__(self):
            self.warns: list[str] = []
            self.prints: list[str] = []

        def warn(self, message, suggestion=None):
            self.warns.append(message)

        def print(self, *args, **kwargs):
            # Match ToolConfig's call shape: a single positional ``str``.
            self.prints.append(args[0] if args else '')

        # Stub the remaining EspLogBase abstract methods so set_logger() accepts us.
        def err(self, message, suggestion=None):
            pass

        def note(self, message):
            pass

        def hint(self, message):
            pass

        def debug(self, message):
            pass

        def set_verbosity(self, mode):
            pass

        def progress_bar(self, cur_iter, total_iters, prefix='', suffix='', bar_length=30):
            pass

    capture = _CaptureLogger()
    previous = EspLog.instance
    EspLog.set_logger(capture)
    try:
        yield capture
    finally:
        EspLog.instance = previous


class TestVerboseFlag:
    """``verbose`` is the single switch that gates user-facing loader output.

    All emissions go through ``esp_pylib.logger.log`` (a proxy for the
    active ``EspLog`` singleton). ``verbose=False`` (the default) is a
    hard mute: tools loading their config at module-import time stay
    silent so library users aren't surprised by spontaneous output.
    """

    # ------------------------------------------------------------------
    # Default behavior: hard-muted.
    # ------------------------------------------------------------------

    def test_default_is_silent_on_invalid_file(self, tmp_path, capture_log):
        # An unparsable candidate must not produce any log output when
        # ``verbose`` is left at its default. Sanity check that the
        # silent path stays silent end-to-end (find → load).
        bad = tmp_path / 'mytool.cfg'
        bad.write_text('[mytool]\nkey=A\nkey=B\n', encoding='utf-8')
        cfg = ToolConfig('mytool', ['mytool.cfg'], search_dirs=[tmp_path])
        assert cfg.find() is None
        cfg.load()
        assert capture_log.warns == []
        assert capture_log.prints == []

    def test_default_is_silent_on_unknown_options_and_loaded(self, tmp_path, capture_log):
        # Default verbose=False: even with valid_options set and a matched
        # file, no warn or print should fire. This is the contract that
        # makes ToolConfig safe to call at module-import time.
        path = tmp_path / 'mytool.cfg'
        _write(path, '[mytool]\nknown=1\nbogus=2\n')
        cfg = ToolConfig(
            'mytool',
            ['mytool.cfg'],
            search_dirs=[tmp_path],
            valid_options=['known'],
        )
        cfg.load()
        assert capture_log.warns == []
        assert capture_log.prints == []

    # ------------------------------------------------------------------
    # verbose=True wires emissions through the log proxy.
    # ------------------------------------------------------------------

    def test_verbose_routes_invalid_file_warning(self, tmp_path, capture_log):
        # Duplicate option triggers configparser.Error → "Ignoring invalid
        # config file ..." should reach log.warn with the standardized text.
        bad = tmp_path / 'mytool.cfg'
        bad.write_text('[mytool]\nkey=A\nkey=B\n', encoding='utf-8')
        cfg = ToolConfig('mytool', ['mytool.cfg'], search_dirs=[tmp_path], verbose=True)
        assert cfg.find() is None
        assert len(capture_log.warns) == 1
        assert capture_log.warns[0].startswith(f'Ignoring invalid config file {bad}: ')

    def test_verbose_routes_unknown_options_singular(self, tmp_path, capture_log):
        path = tmp_path / 'mytool.cfg'
        _write(path, '[mytool]\nknown=1\nbogus=2\n')
        cfg = ToolConfig(
            'mytool',
            ['mytool.cfg'],
            search_dirs=[tmp_path],
            valid_options=['known'],
            verbose=True,
        )
        cfg.load()
        assert capture_log.warns == ['Ignoring unknown config option: bogus']

    def test_verbose_routes_unknown_options_plural_sorted(self, tmp_path, capture_log):
        path = tmp_path / 'mytool.cfg'
        _write(path, '[mytool]\nknown=1\nzzz=2\nbogus=3\nalpha=4\n')
        cfg = ToolConfig(
            'mytool',
            ['mytool.cfg'],
            search_dirs=[tmp_path],
            valid_options=['known'],
            verbose=True,
        )
        cfg.load()
        # Pluralized + alphabetically sorted, regardless of file order.
        assert capture_log.warns == ['Ignoring unknown config options: alpha, bogus, zzz']

    def test_unknown_options_check_skipped_when_valid_options_none(self, tmp_path, capture_log):
        # valid_options=None means "I don't have a known list", so we
        # mustn't emit the unknown-option warning even with verbose=True.
        # The "Loaded ..." line still fires.
        path = tmp_path / 'mytool.cfg'
        _write(path, '[mytool]\nkey=A\nfoo=B\n')
        cfg = ToolConfig('mytool', ['mytool.cfg'], search_dirs=[tmp_path], verbose=True)
        cfg.load()
        assert capture_log.warns == []
        assert capture_log.prints == [f'Loaded custom configuration from {os.path.abspath(str(path))}']

    def test_no_warning_when_all_options_known(self, tmp_path, capture_log):
        path = tmp_path / 'mytool.cfg'
        _write(path, '[mytool]\nknown=1\nalso_known=2\n')
        cfg = ToolConfig(
            'mytool',
            ['mytool.cfg'],
            search_dirs=[tmp_path],
            valid_options=['known', 'also_known'],
            verbose=True,
        )
        cfg.load()
        assert capture_log.warns == []

    def test_verbose_emits_loaded_message_with_abspath(self, tmp_path, capture_log):
        path = tmp_path / 'mytool.cfg'
        _write(path, '[mytool]\nkey=A\n')
        cfg = ToolConfig('mytool', ['mytool.cfg'], search_dirs=[tmp_path], verbose=True)
        cfg.load()
        assert capture_log.prints == [f'Loaded custom configuration from {os.path.abspath(str(path))}']

    def test_verbose_appends_env_var_suffix(self, tmp_path, monkeypatch, capture_log):
        path = tmp_path / 'mytool.cfg'
        _write(path, '[mytool]\nkey=A\n')
        monkeypatch.setenv('MYTOOL_CFGFILE', str(path))
        cfg = ToolConfig(
            'mytool',
            ['mytool.cfg'],
            env_var='MYTOOL_CFGFILE',
            search_dirs=[tmp_path / 'never_searched'],
            verbose=True,
        )
        cfg.load()
        assert capture_log.prints == [
            f'Loaded custom configuration from {os.path.abspath(str(path))} (set with MYTOOL_CFGFILE)'
        ]

    def test_verbose_no_env_suffix_when_search_path_used(self, tmp_path, monkeypatch, capture_log):
        # The env var is set but points at junk; permissive fallback uses
        # the search-path config. The "(set with ...)" suffix must NOT
        # appear because the env var didn't actually contribute the path.
        monkeypatch.setenv('MYTOOL_CFGFILE', str(tmp_path / 'does_not_exist.cfg'))
        path = tmp_path / 'mytool.cfg'
        _write(path, '[mytool]\nkey=A\n')
        cfg = ToolConfig(
            'mytool',
            ['mytool.cfg'],
            env_var='MYTOOL_CFGFILE',
            search_dirs=[tmp_path],
            permissive_env_var=True,
            verbose=True,
        )
        cfg.load()
        assert capture_log.prints == [f'Loaded custom configuration from {os.path.abspath(str(path))}']

    def test_verbose_emits_nothing_when_no_file_found(self, tmp_path, capture_log):
        cfg = ToolConfig('mytool', ['mytool.cfg'], search_dirs=[tmp_path], verbose=True)
        cfg.load()
        assert capture_log.prints == []
        assert capture_log.warns == []

    def test_loaded_message_emitted_only_once_across_repeat_loads(self, tmp_path, capture_log):
        # The "Loaded custom configuration from" line should fire exactly
        # once per cache lifetime, not once per load() call. Otherwise tools
        # that call load() in multiple places would spam the user.
        path = tmp_path / 'mytool.cfg'
        _write(path, '[mytool]\nkey=A\n')
        cfg = ToolConfig('mytool', ['mytool.cfg'], search_dirs=[tmp_path], verbose=True)
        cfg.load()
        cfg.load()
        cfg.load()
        assert len(capture_log.prints) == 1

    def test_reload_lets_loaded_message_fire_again(self, tmp_path, capture_log):
        path = tmp_path / 'mytool.cfg'
        _write(path, '[mytool]\nkey=A\n')
        cfg = ToolConfig('mytool', ['mytool.cfg'], search_dirs=[tmp_path], verbose=True)
        cfg.load()
        cfg.reload()
        cfg.load()
        assert len(capture_log.prints) == 2

    def test_combined_warning_and_loaded_order(self, tmp_path, capture_log):
        # End-to-end: verbose=True with one bad candidate then one good
        # candidate must produce, in order, a warn (bad file) and a print
        # (loaded message). Ordering matters because users read top-down.
        bad = tmp_path / 'a' / 'mytool.cfg'
        bad.parent.mkdir(parents=True)
        bad.write_text('[mytool]\nkey=A\nkey=B\n', encoding='utf-8')
        good = tmp_path / 'b' / 'mytool.cfg'
        _write(good, '[mytool]\nknown=1\nbogus=2\n')
        cfg = ToolConfig(
            'mytool',
            ['mytool.cfg'],
            search_dirs=[bad.parent, good.parent],
            valid_options=['known'],
            verbose=True,
        )
        cfg.load()
        assert len(capture_log.warns) == 2
        assert capture_log.warns[0].startswith(f'Ignoring invalid config file {bad}: ')
        assert capture_log.warns[1] == 'Ignoring unknown config option: bogus'
        assert capture_log.prints == [f'Loaded custom configuration from {os.path.abspath(str(good))}']

    # ------------------------------------------------------------------
    # Explicit ``logger=`` injection bypasses the global EspLog singleton.
    # ------------------------------------------------------------------

    def test_explicit_logger_bypasses_global_singleton(self, tmp_path, capture_log):
        # Regression-prevention for the singleton-fragility refactor:
        # ``ToolConfig(logger=...)`` must route through the *given* logger,
        # not whatever ``EspLog.instance`` happens to be. We install a
        # capture as the global singleton AND pass a different capture
        # via ``logger=``; only the explicit one should see the calls.
        from esp_pylib.logger import EspLogBase

        class _LocalCapture(EspLogBase):
            def __init__(self):
                self.warns: list[str] = []
                self.prints: list[str] = []

            def warn(self, message, suggestion=None):
                self.warns.append(message)

            def print(self, *args, **kwargs):
                self.prints.append(args[0] if args else '')

            def err(self, message, suggestion=None):
                pass  # noqa: E704

            def note(self, message):
                pass  # noqa: E704

            def hint(self, message):
                pass  # noqa: E704

            def debug(self, message):
                pass  # noqa: E704

            def set_verbosity(self, mode):
                pass  # noqa: E704

            def progress_bar(self, cur_iter, total_iters, prefix='', suffix='', bar_length=30):
                pass  # noqa: E704

        local = _LocalCapture()
        path = tmp_path / 'mytool.cfg'
        _write(path, '[mytool]\nknown=1\nbogus=2\n')
        cfg = ToolConfig(
            'mytool',
            ['mytool.cfg'],
            search_dirs=[tmp_path],
            valid_options=['known'],
            verbose=True,
            logger=local,
        )
        cfg.load()
        # Explicit logger took the calls.
        assert local.warns == ['Ignoring unknown config option: bogus']
        assert local.prints == [f'Loaded custom configuration from {os.path.abspath(str(path))}']
        # Global singleton (capture_log) saw nothing.
        assert capture_log.warns == []
        assert capture_log.prints == []

    def test_logger_none_falls_back_to_global_proxy(self, tmp_path, capture_log):
        # The default ``logger=None`` must resolve to ``esp_pylib.logger.log``,
        # which dispatches to ``EspLog.instance`` — i.e. the existing
        # capture installed by the fixture. This guards the "do nothing
        # special and the proxy still works" path that monitor and other
        # consumers rely on when they don't pass an explicit logger.
        path = tmp_path / 'mytool.cfg'
        _write(path, '[mytool]\nkey=A\n')
        cfg = ToolConfig('mytool', ['mytool.cfg'], search_dirs=[tmp_path], verbose=True)
        cfg.load()
        assert capture_log.prints == [f'Loaded custom configuration from {os.path.abspath(str(path))}']


# ---------------------------------------------------------------------------
# Module-level smoke test: importing config.py must not require any extra deps
# (no pyserial, no rich, no click). Mirrors the same check we run for ws.py.
# ---------------------------------------------------------------------------


class TestNoOptionalDepsRequired:
    def test_module_exports(self):
        assert ToolConfig.__module__ == 'esp_pylib.config'
        assert hasattr(config_mod, 'ToolConfig')

    def test_works_without_env_var_set(self, tmp_path):
        # Sanity: ensure no implicit dependency on the env var being defined.
        os.environ.pop('NONEXISTENT_TEST_VAR', None)
        cfg = ToolConfig('mytool', ['mytool.cfg'], env_var='NONEXISTENT_TEST_VAR', search_dirs=[tmp_path])
        assert cfg.find() is None
