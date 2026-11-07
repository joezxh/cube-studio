"""Task 11 契约：三模板注册合法 + flag 名与各 start.py argparse 逐字对齐。"""
import ast
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
TPL_PATH = ROOT / "myapp" / "init" / "init-job-template.json"

OPS = {
    "lerobot-import": "lerobot_import",
    "lerobot-train": "lerobot_train",
    "lerobot-eval": "lerobot_eval",
}

ARG_FIELDS = {"choice", "default", "describe", "editable", "item_type",
              "label", "placeholder", "range", "require", "type"}


def _start_flags(op_dir):
    """AST 静态提取 start.py 中全部 add_argument("--x") flag 名（不执行模块）。"""
    src = (ROOT / "job-template" / "job" / op_dir / "start.py").read_text(
        encoding="utf-8")
    flags = set()
    for node in ast.walk(ast.parse(src)):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "add_argument"
                and node.args and isinstance(node.args[0], ast.Constant)):
            v = node.args[0].value
            if isinstance(v, str) and v.startswith("--"):
                flags.add(v)
    return flags


def _start_flag_kwargs(op_dir):
    """AST 提取 start.py add_argument 的 (flag, {kwarg名}) 与位置 bool 形态。"""
    src = (ROOT / "job-template" / "job" / op_dir / "start.py").read_text(
        encoding="utf-8")
    out = {}
    for node in ast.walk(ast.parse(src)):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "add_argument"
                and node.args and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
                and node.args[0].value.startswith("--")):
            out[node.args[0].value] = {k.arg for k in node.keywords}
    return out


def _templates():
    return json.loads(TPL_PATH.read_text(encoding="utf-8"))


def test_three_templates_registered():
    d = _templates()
    for name in OPS:
        assert name in d, name
        t = d[name]
        assert t["job_template_name"] == name
        assert t["gitpath"] == "/job-template/job/%s" % OPS[name]
        assert t["job_template_command"] == "python3 start.py"
        img = t["image_name"]
        if name == "lerobot-import":
            assert img.endswith("lerobot:import-cpu")
        else:
            assert img.endswith("lerobot:gpu-0.6.2")


def test_template_flags_match_start_argparse():
    d = _templates()
    for name, op_dir in OPS.items():
        start_flags = _start_flags(op_dir)
        tpl_flags = set()
        for group in d[name]["job_template_args"].values():
            tpl_flags.update(group)
        # 模板每个 flag 必须被 start.py argparse 接受（未知 flag 即运行期炸点）
        assert tpl_flags <= start_flags, (name, tpl_flags - start_flags)
        # start.py 的必填 flag 必须全部出现在模板中（base_dir 为测试覆盖点除外）
        required = start_flags - {"--base_dir"}
        assert required <= tpl_flags, (name, required - tpl_flags)


def test_arg_field_schema_and_bool_defaults():
    d = _templates()
    for name in OPS:
        for group in d[name]["job_template_args"].values():
            for flag, spec in group.items():
                assert set(spec) == ARG_FIELDS, (name, flag)
                if spec["type"] in ("bool", "int"):
                    assert isinstance(spec["default"], str), (name, flag)
                if spec["choice"]:
                    assert spec["type"] == "str", (name, flag)


def test_gpu_templates_have_workdir():
    # C1 回归：command 为相对路径 start.py 时，平台工作目录取
    # job_template_workdir，镜像/模板皆空则启动即炸（仓库存例皆声明 workdir）
    d = _templates()
    for name, op_dir in OPS.items():
        t = d[name]
        assert t.get("job_template_workdir") == "/opt/%s" % op_dir, name


def test_bool_flags_accept_bare_form():
    # C2 回归：平台对真布尔只渲染裸 flag，argparse 须接受零参数形态
    # （nargs="?" + const）或 action=store_true；否则开启即 exit 2
    d = _templates()
    for name, op_dir in OPS.items():
        kw = _start_flag_kwargs(op_dir)
        for group in d[name]["job_template_args"].values():
            for flag, spec in group.items():
                if spec["type"] == "bool":
                    kws = kw.get(flag, set())
                    assert ("nargs" in kws and "const" in kws) or (
                        "action" in kws), (name, flag, sorted(kws))
