"""
账号解析模块 - 解析账号文件

支持格式（冒号分隔）:
  格式1: 账号:密码:邮箱:2FA (4字段，邮箱包含@)
  格式2: 账号:密码:2FA (3字段)
  格式3: 账号:密码:2FA:token:邮箱:邮箱密码:邮箱ClientId:邮箱Token (8字段完整格式)

字段说明:
  - 账号: Twitter/X 用户名
  - 密码: 账号密码
  - 2FA: TOTP 密钥
  - token: X token（可选）
  - 邮箱: 关联邮箱（用于异常活动验证）
  - 邮箱密码: 邮箱密码
  - 邮箱ClientId: 邮箱 Client ID
  - 邮箱Token: 邮箱 Token
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from ..proxy.parser import ProxyConfig
from ..core.errors import AccountParseError as BaseAccountParseError


@dataclass
class AccountInfo:
    """账号信息"""
    username: str
    password: str
    totp_secret: Optional[str] = None
    token: Optional[str] = None  # X token
    email: Optional[str] = None  # 邮箱（用于异常活动验证）
    email_password: Optional[str] = None  # 邮箱密码
    email_client_id: Optional[str] = None  # 邮箱 Client ID
    email_token: Optional[str] = None  # 邮箱 Token
    proxy: Optional[ProxyConfig] = None  # 代理现在是可选的

    @property
    def id(self) -> str:
        """返回账号标识（用于文件名等）"""
        return self.username.replace("@", "_at_")

    def __str__(self) -> str:
        """返回脱敏的账号信息"""
        proxy_str = str(self.proxy) if self.proxy else "无代理"
        email_str = self.email[:10] + "..." if self.email and len(self.email) > 10 else self.email
        return f"Account({self.username}, email={email_str}, proxy={proxy_str})"


# 使用统一异常模型，保持向后兼容
AccountParseError = BaseAccountParseError


def parse_account_line(line: str, line_number: int = 0) -> AccountInfo:
    """
    解析单行账号信息

    支持多种格式:
      格式1: 账号:密码:邮箱:2FA (4字段，第3字段包含@表示是邮箱)
      格式2: 账号:密码:2FA (3字段)
      格式3: 账号:密码:2FA:token:邮箱:邮箱密码:邮箱ClientId:邮箱Token (8字段)

    Args:
        line: 账号行
        line_number: 行号（用于错误提示）

    Returns:
        AccountInfo 对象

    Raises:
        AccountParseError: 解析失败时抛出
    """
    if not line or not line.strip():
        raise AccountParseError("账号行不能为空", line_number, line)

    line = line.strip()

    # 跳过注释行
    if line.startswith("#"):
        raise AccountParseError("注释行", line_number, line)

    # 使用冒号分隔
    parts = line.split(":")

    # 最少需要 3 个部分
    if len(parts) < 3:
        raise AccountParseError(
            f"格式错误，期望至少 3 个字段，实际 {len(parts)} 个",
            line_number,
            line
        )

    username = parts[0].strip()
    password = parts[1].strip()

    if not username:
        raise AccountParseError("用户名不能为空", line_number, line)
    if not password:
        raise AccountParseError("密码不能为空", line_number, line)

    # 初始化可选字段
    totp_secret = None
    token = None
    email = None
    email_password = None
    email_client_id = None
    email_token = None

    if len(parts) == 3:
        # 格式2: 账号:密码:2FA
        totp_secret = parts[2].strip() or None
    elif len(parts) == 4:
        # 检查第3个字段是否是邮箱（包含@）
        field3 = parts[2].strip()
        field4 = parts[3].strip()

        if "@" in field3:
            # 格式1: 账号:密码:邮箱:2FA
            email = field3
            totp_secret = field4 or None
        else:
            # 可能是: 账号:密码:2FA:token
            totp_secret = field3 or None
            token = field4 or None
    else:
        # 格式3: 账号:密码:2FA:token:邮箱:邮箱密码:邮箱ClientId:邮箱Token
        totp_secret = parts[2].strip() or None
        token = parts[3].strip() if len(parts) > 3 and parts[3].strip() else None
        email = parts[4].strip() if len(parts) > 4 and parts[4].strip() else None
        email_password = parts[5].strip() if len(parts) > 5 and parts[5].strip() else None
        email_client_id = parts[6].strip() if len(parts) > 6 and parts[6].strip() else None
        email_token = parts[7].strip() if len(parts) > 7 and parts[7].strip() else None

    return AccountInfo(
        username=username,
        password=password,
        totp_secret=totp_secret,
        token=token,
        email=email,
        email_password=email_password,
        email_client_id=email_client_id,
        email_token=email_token,
        proxy=None
    )


def parse_accounts_file(file_path: Path) -> List[AccountInfo]:
    """
    解析账号文件

    Args:
        file_path: 账号文件路径

    Returns:
        账号列表

    Raises:
        FileNotFoundError: 文件不存在
        AccountParseError: 解析失败
    """
    if not file_path.exists():
        raise FileNotFoundError(f"账号文件不存在: {file_path}")

    accounts: List[AccountInfo] = []
    errors: List[str] = []

    with open(file_path, "r", encoding="utf-8") as f:
        for line_number, line in enumerate(f, start=1):
            line = line.strip()

            # 跳过空行和注释
            if not line or line.startswith("#"):
                continue

            try:
                account = parse_account_line(line, line_number)
                accounts.append(account)
            except AccountParseError as e:
                if "注释行" not in str(e):
                    errors.append(str(e))

    if errors:
        error_msg = "\n".join(errors[:5])  # 只显示前5个错误
        if len(errors) > 5:
            error_msg += f"\n... 还有 {len(errors) - 5} 个错误"
        raise AccountParseError(f"账号文件解析错误:\n{error_msg}")

    return accounts


def load_accounts(file_path: str | Path) -> List[AccountInfo]:
    """
    加载账号文件（便捷函数）

    Args:
        file_path: 账号文件路径（字符串或 Path）

    Returns:
        账号列表
    """
    return parse_accounts_file(Path(file_path))
