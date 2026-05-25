# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""Tests for esp_pylib.cli_options."""

import rich_click as click
from click.testing import CliRunner

from esp_pylib.cli_options import EspRichGroup
from esp_pylib.cli_options import MutuallyExclusiveOption
from esp_pylib.cli_options import OptionEatAll


class TestMutuallyExclusiveOption:
    def test_rejects_conflicting_flags(self):
        @click.command()
        @click.option(
            '--compress',
            is_flag=True,
            cls=MutuallyExclusiveOption,
            exclusive_with=['no_compress'],
        )
        @click.option(
            '--no-compress',
            '-u',
            is_flag=True,
            cls=MutuallyExclusiveOption,
            exclusive_with=['compress'],
        )
        def cmd(compress, no_compress):
            click.echo('ok')

        runner = CliRunner()
        result = runner.invoke(cmd, ['--compress', '--no-compress'])
        assert result.exit_code != 0
        assert 'mutually exclusive' in result.output.lower()

    def test_allows_single_flag(self):
        @click.command()
        @click.option(
            '--compress',
            is_flag=True,
            cls=MutuallyExclusiveOption,
            exclusive_with=['no_compress'],
        )
        @click.option(
            '--no-compress',
            is_flag=True,
            cls=MutuallyExclusiveOption,
            exclusive_with=['compress'],
        )
        def cmd(compress, no_compress):
            click.echo(f'compress={compress}')

        runner = CliRunner()
        result = runner.invoke(cmd, ['--compress'])
        assert result.exit_code == 0
        assert 'compress=True' in result.output

    def test_help_mentions_exclusive_peers(self):
        @click.command()
        @click.option(
            '--a',
            is_flag=True,
            help='Option A.',
            cls=MutuallyExclusiveOption,
            exclusive_with=['b'],
        )
        def cmd(a):
            pass

        runner = CliRunner()
        result = runner.invoke(cmd, ['--help'])
        assert '--b' in result.output

    def test_help_without_base_text_starts_with_note(self):
        opt = MutuallyExclusiveOption(['--a'], is_flag=True, exclusive_with=['b'])
        assert opt.help.startswith('NOTE: This argument is mutually exclusive')

    def test_help_with_base_text_separates_note(self):
        opt = MutuallyExclusiveOption(
            ['--a'],
            is_flag=True,
            help='Option A.',
            exclusive_with=['b'],
        )
        assert opt.help == ('Option A. NOTE: This argument is mutually exclusive with arguments: --b.')

    def test_error_uses_real_long_option_when_name_differs(self):
        @click.command()
        @click.option(
            '--port-x',
            'port_alt',
            is_flag=True,
            cls=MutuallyExclusiveOption,
            exclusive_with=['other'],
        )
        @click.option(
            '--other',
            is_flag=True,
            cls=MutuallyExclusiveOption,
            exclusive_with=['port_alt'],
        )
        def cmd(port_alt, other):
            pass

        runner = CliRunner()
        result = runner.invoke(cmd, ['--port-x', '--other'])
        assert result.exit_code != 0
        assert '--port-x' in result.output
        assert '--port-alt' not in result.output


class _TokenListType(click.ParamType):
    """Minimal stand-in for esptool ``AddrFilenamePairType`` (expects ``list[str]``)."""

    name = 'token-list'

    def convert(self, value, param, ctx):
        if not isinstance(value, list):
            raise click.BadParameter('expected a list of tokens')
        return tuple(value)


class TestOptionEatAll:
    def test_without_multiple_passes_token_list_to_type(self):
        """``--encrypt-files`` pattern: one ``convert()`` call with all eaten tokens."""

        @click.command()
        @click.option('--pairs', type=_TokenListType(), cls=OptionEatAll)
        def cmd(pairs):
            click.echo(pairs)

        runner = CliRunner()
        result = runner.invoke(cmd, ['--pairs', '0x1000', 'a.bin', '0x2000', 'b.bin'])
        assert result.exit_code == 0
        assert result.output.strip() == "('0x1000', 'a.bin', '0x2000', 'b.bin')"

    def test_collects_values_until_next_option(self):
        @click.command()
        @click.option('--port-filter', multiple=True, type=str, cls=OptionEatAll)
        @click.option('--verbose', is_flag=True)
        def cmd(port_filter, verbose):
            click.echo(f'filters={list(port_filter)!r} verbose={verbose}')

        runner = CliRunner()
        result = runner.invoke(
            cmd,
            ['--port-filter', 'vid=0x303A', 'name=USB', '--verbose'],
        )
        assert result.exit_code == 0
        assert "filters=['vid=0x303A', 'name=USB']" in result.output
        assert 'verbose=True' in result.output

    def test_eat_all_with_multiple_uses(self):
        @click.command()
        @click.option('--key', cls=OptionEatAll, multiple=True, type=click.File('rb'))
        def cmd(key):
            click.echo(len(key))

        runner = CliRunner()
        with runner.isolated_filesystem():
            open('a.pem', 'w').write('a')
            open('b.pem', 'w').write('b')
            result = runner.invoke(cmd, ['--key', 'a.pem', '--key', 'b.pem'])
        assert result.exit_code == 0
        assert '2' in result.output

    def test_stops_at_subcommand_with_esprichgroup(self):
        @click.group(cls=EspRichGroup)
        @click.option('--port-filter', multiple=True, type=str, cls=OptionEatAll)
        def cli(port_filter):
            click.echo(f'filters={list(port_filter)!r}')

        @cli.command()
        def flash():
            click.echo('flash')

        runner = CliRunner()
        result = runner.invoke(cli, ['--port-filter', 'vid=0x303A', 'flash'])
        assert result.exit_code == 0
        assert "filters=['vid=0x303A']" in result.output
        assert 'flash' in result.output
