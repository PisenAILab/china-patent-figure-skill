# PyPI 发布（包名 `china-patent-figure-skill`）

> 上传是对外发布动作，受首次外发门禁。本文只写**怎么做**。本仓库的任何自动化都不上传。

## 事实

| 项 | 值 |
| --- | --- |
| 包名 | `china-patent-figure-skill`（上传前核查 PyPI 占用） |
| 包目录 | `patent_figure_kit`（不改；`import patent_figure_kit` 仍成立） |
| 入口命令 | `pfk`（主）、`patent-figure-kit`（= `pfk start`） |
| 版本来源 | `scripts/pfk_cli.py` 的 `__version__`（hatch `dynamic`） |
| 构建后端 | hatchling 1.27.0（`[build-system]` 锁定） |
| 产物 | `dist/china_patent_figure_skill-<版本>-py3-none-any.whl`（约 1.2 MB）、`dist/china_patent_figure_skill-<版本>.tar.gz`（约 7 MB，含 tests / examples / webui） |
| 运行依赖 | 与 `requirements-pinned.txt` 逐字一致（`tests/test_deploy_tools.py` 守着）；`[web]` extras 与 `requirements-web.txt` 一致 |
| Python | 3.9–3.12（`requires-python = ">=3.9,<3.13"`，由 cadquery-ocp 7.7.2 的轮子范围决定） |

## 本地构建与检查（任何人都可以做，不外发）

```bash
python3 -m pip install -U build==1.2.2.post1 twine==6.1.0
rm -rf dist && python3 -m build --outdir dist
python3 -m twine check dist/*
```

预期：`Successfully built china_patent_figure_skill-<版本>.tar.gz and china_patent_figure_skill-<版本>-py3-none-any.whl`，twine 两行 `PASSED`。

装进仓库外的全新环境并跑完整验收（含 N10 金样）：

```bash
python3.12 -m venv /tmp/cnpf-venv
/tmp/cnpf-venv/bin/python -m pip install -U pip
/tmp/cnpf-venv/bin/python -m pip install "dist/china_patent_figure_skill-<版本>-py3-none-any.whl[web,test]"
/tmp/cnpf-venv/bin/pfk paths --check
/tmp/cnpf-venv/bin/pfk doctor --profile web
cd /tmp && /tmp/cnpf-venv/bin/pfk acceptance
```

预期最后一行：`通过 19 ／ 未通过 0 ／ 跳过 0`，退出码 0。`golden-matrix.yml` 在三平台 × 三个 Python 上做同样的事。

## 上传（门禁通过后，由用户执行）

1. **先传 TestPyPI**，在全新环境安装、跑 `pfk acceptance`：

   ```bash
   python3 -m twine upload --repository testpypi dist/*
   python3 -m pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ "china-patent-figure-skill[web]"
   ```

2. 正式上传：

   ```bash
   python3 -m twine upload dist/*
   ```

   凭据用 PyPI API token（`__token__` + 令牌），只放 `~/.pypirc`（权限 0600）或环境变量 `TWINE_PASSWORD`，**不进仓库、不写进任何 Markdown**。

3. 之后若改用 GitHub Actions 的 Trusted Publishing（OIDC，免令牌）：在 PyPI 项目设置里登记 `PisenAILab/china-patent-figure-skill` 的发布工作流名，工作流加 `permissions: id-token: write` 并用 `pypa/gh-action-pypi-publish`。本仓库目前**没有**这样的工作流，这是有意的：首发由人上传。

## 已知限制

- PyPI 页面的长描述取自 `README.md`，其中的相对路径图片与链接（`docs/assets/...`）在 PyPI 上不会显示。首发可接受；之后若在意，在 `pyproject.toml` 加 hatch 元数据钩子把相对路径改写成 `https://raw.githubusercontent.com/PisenAILab/china-patent-figure-skill/main/...`。
- sdist 含 `tests/` 与 `examples/`（约 7 MB），为的是 `pfk acceptance` 能在任何环境里跑；不想要可在 `[tool.hatch.build.targets.sdist]` 里排除。
- 包名 `china-patent-figure-skill`；旧名 `patent-figure-kit` 不在 PyPI 上，无需占位。
