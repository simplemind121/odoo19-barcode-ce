# odoo19-barcode-ce（中文说明）

为 **Odoo 19 社区版** 提供摄像头和扫码枪扫码能力：仓库扫码应用（收货、发货、
调拨、盘点、批次/序列号、包裹、GS1、批量和波次调拨）、扫码建档、热敏标签
打印，以及销售、采购、POS 里的扫码。

全部代码为独立实现，未使用 Odoo 企业版代码，以 LGPL-3 授权发布。

> English: [README.md](README.md)

## 模块

| 模块 | 作用 |
| --- | --- |
| [`barcode_camera_ce`](barcode_camera_ce/README.md) | 摄像头扫码底层：导航栏扫码按钮、连续扫码窗口、提示音和震动 |
| [`product_barcode_quick`](product_barcode_quick/README.md) | 「条码」应用：扫码查商品、未知码建档、店内码、校验位检查、热敏标签（PDF） |
| [`stock_barcode_ce`](stock_barcode_ce/README.md) | 仓库扫码主体：出入库、调拨、盘点、批次、包裹、GS1、报废、退货、扫码规则、扫码日志 |
| [`stock_barcode_print_ce`](stock_barcode_print_ce/README.md) | 通过本地代理直连 TSPL/ZPL 标签机 |
| [`sale_barcode_ce`](sale_barcode_ce/README.md) | 报价单扫码加行；发货后开票 |
| [`purchase_barcode_ce`](purchase_barcode_ce/README.md) | 询价单扫码加行；收货后生成账单 |
| [`pos_barcode_ce`](pos_barcode_ce/README.md) | POS 扫到未知码时可当场建档并加入订单 |

安装 `stock_barcode_ce` 即可；需要直连打印时再装 `stock_barcode_print_ce`。
销售、采购、POS 三个模块会在对应应用已安装时自动安装。

## 运行要求

*   Odoo 19.0 社区版。
*   HTTPS：摄像头只在 HTTPS 下可用，扫码枪不受影响。
*   `wkhtmltopdf 0.12.6.1 (with patched qt)`：PDF 标签尺寸依赖它，官方
    `odoo:19` 镜像自带。
*   `workers > 0` 且反向代理开启 WebSocket：用于多台设备实时刷新，不满足时
    自动退回定时刷新。

## 快速开始

```bash
./deploy-barcode-ce.sh --check   # 只检查环境，不改任何东西
./deploy-barcode-ce.sh           # 部署到 staging
./deploy-barcode-ce.sh --prod    # 部署到生产
```

脚本不会备份数据库，部署正式库前请先自行 `pg_dump`。

本地试用和开发：

```bash
./dev-env.sh          # 建隔离的开发环境（端口 8169 / 5442）
./scripts/test.sh     # 跑全套测试
```

## 文档

| 文档 | 内容 |
| --- | --- |
| [一分钟上手.md](一分钟上手.md) | 部署、开发两条最短路径 |
| [docs/README_安装与验收.md](docs/README_安装与验收.md) | 安装、配置、使用入口、验收清单 |
| [docs/PROJECT_HISTORY.md](docs/PROJECT_HISTORY.md) | 设计决策、踩过的坑、验证结论 |
| [docs/compatibility.md](docs/compatibility.md) | 与 Odoo 19 社区版原生行为的差异（英文） |
| [docs/architecture.md](docs/architecture.md) | 架构说明（英文） |
| [docs/scanner-api.md](docs/scanner-api.md) | 扫码接口参考（英文） |
| [docs/development.md](docs/development.md) | 开发环境、测试、约定（英文） |
| [docs/deployment.md](docs/deployment.md) | 部署与升级（英文） |
| [docs/label-printing.md](docs/label-printing.md) | 标签打印代理（英文） |
| [CHANGELOG.md](CHANGELOG.md) | 版本变更记录 |

## 当前状态

2.1 版（`stock_barcode_ce` 19.0.2.1.0），83 项自动化测试，其中 11 项在真实
浏览器中操作，每次推送由 GitHub Actions 自动运行。

需要真机验收的部分：摄像头取景、各品牌扫码枪、标签机出纸效果。

尚未实现：生产（MRP）和质检扫码、IoT 盒子打印、寄售库存、套件商品、盘点
离线。

## 参与贡献与安全问题

*   贡献方式见 [CONTRIBUTING.md](CONTRIBUTING.md)。
*   安全漏洞请按 [SECURITY.md](SECURITY.md) 私下报告，不要开公开 issue。

## 许可与声明

LGPL-3.0-or-later，见 [LICENSE](LICENSE)。

本项目不是 Odoo 官方产品，与 Odoo S.A. 没有关联。“Odoo”是 Odoo S.A. 的商标。
