from __future__ import annotations

import json
import subprocess
from pathlib import Path


def run_markdown_table_helper(expression: str):
    root = Path(__file__).resolve().parents[1]
    source = (root / "src" / "markdown_table.ts").read_text(encoding="utf-8")
    script = f"""
const ts = require('typescript');
const source = {json.dumps(source)};
const output = ts.transpileModule(source, {{
  compilerOptions: {{ module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 }}
}}).outputText;
const module = {{ exports: {{}} }};
new Function('exports', 'module', output)(module.exports, module);
const result = {expression};
console.log(JSON.stringify(result));
"""
    completed = subprocess.run(
        ["node", "-e", script],
        cwd=str(root),
        text=True,
        capture_output=True,
        check=True,
    )
    return json.loads(completed.stdout)


def test_markdown_table_helpers_accept_blockquoted_tables_and_alignment():
    lines = [
        "> | 游戏 | 状态 |",
        "> | :--- | ---: |",
        "> | CrossCode | 已安装 |",
    ]

    assert run_markdown_table_helper(
        f"module.exports.isTableStart({json.dumps(lines)}, 0)"
    ) is True
    assert run_markdown_table_helper(
        "module.exports.splitTableRow('> | CrossCode | 已安装 |')"
    ) == ["CrossCode", "已安装"]
    assert run_markdown_table_helper(
        "module.exports.tableAlignments('> | :--- | ---: |')"
    ) == ["left", "right"]
