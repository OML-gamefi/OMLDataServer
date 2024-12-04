import bcrypt
import logging

logger = logging.getLogger(__name__)

def hash_password(password: str) -> str:
    """
    对密码进行哈希加密
    :param password: 原始密码
    :return: 加密后的密码
    """
    try:
        # 生成salt并加密
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
        return hashed.decode('utf-8')
    except Exception as e:
        logger.error(f"密码加密失败: {str(e)}")
        raise

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    验证密码是否正确
    :param plain_password: 原始密码
    :param hashed_password: 加密后的密码
    :return: 是否匹配
    """
    try:
        return bcrypt.checkpw(
            plain_password.encode('utf-8'),
            hashed_password.encode('utf-8')
        )
    except Exception as e:
        logger.error(f"密码验证失败: {str(e)}")
        return False 