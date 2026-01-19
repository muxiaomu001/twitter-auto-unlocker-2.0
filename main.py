#!/usr/bin/env python3
"""
Twitter 自动解锁工具 2.0 - CLI 入口

功能:
- 批量解锁被锁定的 Twitter 账号
- 使用 BitBrowser 指纹浏览器
- 使用 YesCaptcha 处理验证码（插件/API 两种模式）

Usage:
    python main.py --input accounts.txt
    python main.py --input accounts.txt --config config.yaml
    python main.py --input accounts.txt --api-key YOUR_KEY --concurrency 5

版本: 2.0 - BitBrowser + YesCaptcha
"""

import argparse
import asyncio
import sys
from pathlib import Path

from x_unlocker.account.parser import parse_accounts_file
from x_unlocker.queue.worker import run_batch_unlock
from x_unlocker.core.config import AppConfig, load_config
from x_unlocker.utils.logger import get_logger, setup_file_logging

logger = get_logger(__name__)


def parse_args() -> argparse.Namespace:
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="Twitter 自动解锁工具 2.0",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python main.py --input accounts.txt --config config.yaml
  python main.py --input accounts.txt --api-key YOUR_YESCAPTCHA_KEY
  python main.py --input accounts.txt --api-key KEY --concurrency 10

账号文件格式:
  用户名:密码:2FA密钥:代理IP
  代理格式: ip:端口:用户名:密码 (SOCKS5)

验证码处理:
  - 插件模式（推荐）：在比特浏览器中安装 YesCaptcha 人机助手
  - API 模式：代码自动截图识别并模拟点击
        """
    )

    parser.add_argument(
        "--input", "-i",
        required=True,
        type=Path,
        help="账号文件路径"
    )

    parser.add_argument(
        "--config", "-c",
        type=Path,
        default=Path("config.yaml"),
        help="配置文件路径 (默认: config.yaml)"
    )

    parser.add_argument(
        "--api-key",
        help="YesCaptcha API Key (优先于配置文件)"
    )

    parser.add_argument(
        "--output", "-o",
        type=Path,
        help="输出目录 (默认: ./output)"
    )

    parser.add_argument(
        "--concurrency",
        type=int,
        help="最大并发浏览器数 (默认: 5)"
    )

    parser.add_argument(
        "--max-attempts",
        type=int,
        help="每个账号最大重试次数 (默认: 3)"
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        help="开启调试日志"
    )

    parser.add_argument(
        "--captcha-mode",
        choices=["plugin", "api"],
        help="验证码处理模式: plugin(插件) 或 api(图像识别)"
    )

    return parser.parse_args()


async def main() -> int:
    """主函数"""
    args = parse_args()

    # 加载配置
    try:
        config = load_config(
            config_path=args.config if args.config.exists() else None,
            api_key=args.api_key,
            output_dir=args.output,
            concurrency=args.concurrency,
            max_attempts=args.max_attempts,
            debug=args.debug,
        )
    except Exception as e:
        logger.error(f"加载配置失败: {e}")
        return 1

    # 覆盖验证码模式（如果命令行指定）
    if args.captcha_mode:
        config.captcha.mode = args.captcha_mode

    # 设置日志级别
    if config.debug:
        import logging
        logging.getLogger().setLevel(logging.DEBUG)

    # 检查 API Key
    if not config.captcha.api_key:
        logger.error("未提供 YesCaptcha API Key")
        logger.error("请使用 --api-key 参数或在配置文件中设置 captcha.api_key")
        return 1

    # 创建输出目录
    config.output.dir.mkdir(parents=True, exist_ok=True)

    # 设置文件日志
    if config.logging.file_output:
        log_file = config.output.dir / config.logging.file_name
        setup_file_logging(log_file)

    # 解析账号文件
    logger.info(f"读取账号文件: {args.input}")
    try:
        accounts = parse_accounts_file(args.input)
    except Exception as e:
        logger.error(f"读取账号文件失败: {e}")
        return 1

    if not accounts:
        logger.error("账号文件为空或格式错误")
        return 1

    logger.info(f"已加载 {len(accounts)} 个账号")

    # 显示配置信息
    logger.info("=" * 50)
    logger.info("Twitter Auto Unlocker 2.0")
    logger.info("=" * 50)
    logger.info("配置信息:")
    logger.info(f"  浏览器: BitBrowser (API: {config.browser.api_url})")
    logger.info(f"  验证码: YesCaptcha ({config.captcha.mode} 模式)")
    logger.info(f"  并发数: {config.concurrency.max_browsers}")
    logger.info(f"  最大重试: {config.retry.max_attempts}")
    logger.info(f"  输出目录: {config.output.dir}")
    logger.info("=" * 50)

    # 运行批量解锁
    try:
        stats = await run_batch_unlock(
            accounts=accounts,
            config=config,
        )

        # 输出结果摘要
        logger.info("=" * 50)
        logger.info("处理完成!")
        logger.info(f"  {stats.summary()}")
        logger.info("=" * 50)

        # 输出详细结果
        if stats.results:
            logger.info("详细结果:")
            for result in stats.results:
                status = "✓" if result.status.value == "success" else "✗"
                duration = f"{result.duration:.1f}s" if result.duration else "N/A"
                logger.info(f"  {status} {result.account_id}: {result.message} ({duration})")

        # 生成结果汇总文件
        summary_file = config.output.dir / "summary.txt"
        with open(summary_file, "w", encoding="utf-8") as f:
            f.write(f"Twitter 解锁结果汇总\n")
            f.write(f"{'=' * 40}\n")
            f.write(f"{stats.summary()}\n\n")
            f.write(f"详细结果:\n")
            for result in stats.results:
                status = "成功" if result.status.value == "success" else "失败"
                f.write(f"  [{status}] {result.account_id}: {result.message}\n")

        logger.info(f"结果汇总已保存到: {summary_file}")

        # 生成成功/失败账号列表
        success_file = config.output.dir / config.output.success_file
        failed_file = config.output.dir / config.output.failed_file

        success_accounts = [r.account_id for r in stats.results if r.status.value == "success"]
        failed_accounts = [r.account_id for r in stats.results if r.status.value != "success"]

        if success_accounts:
            with open(success_file, "w", encoding="utf-8") as f:
                f.write("\n".join(success_accounts))
            logger.info(f"成功账号列表: {success_file}")

        if failed_accounts:
            with open(failed_file, "w", encoding="utf-8") as f:
                f.write("\n".join(failed_accounts))
            logger.info(f"失败账号列表: {failed_file}")

        return 0 if stats.failed == 0 else 1

    except KeyboardInterrupt:
        logger.info("用户中断，正在退出...")
        return 130

    except Exception as e:
        logger.error(f"运行异常: {e}")
        if config.debug:
            import traceback
            traceback.print_exc()
        return 1


def run():
    """入口点"""
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.info("用户中断")
        sys.exit(130)


if __name__ == "__main__":
    run()
