from flask import request

messages = {
    "UNAUTHORIZED": {"zh": "请先登录。", "en": "Please sign in."},
    "INVALID_CREDENTIALS": {"zh": "用户名或密码错误。", "en": "Incorrect username or password."},
    "FORBIDDEN": {"zh": "您没有权限执行此操作。", "en": "You do not have permission to perform this action."},
    "VALIDATION_ERROR": {"zh": "请检查输入的参数。", "en": "Please check the supplied fields."},
    "UNSUPPORTED_MEDIA_TYPE": {"zh": "请使用 JSON 格式提交。", "en": "Please submit the request as JSON."},
    "NOT_FOUND": {"zh": "找不到请求的资源。", "en": "The requested resource was not found."},
    "PARTICIPANT_NOT_FOUND": {"zh": "找不到该编号对应的参与者。", "en": "No participant has that code."},
    "CLAIM_NOT_FOUND": {"zh": "参与者编号与登记邮箱不匹配。", "en": "The participant code and registered email do not match."},
    "RATE_LIMITED": {"zh": "领取请求过于频繁，请稍后重试。", "en": "Too many claim attempts. Please try again later."},
    "INVALID_QR": {"zh": "二维码无效或已失效。", "en": "This QR code is invalid or has expired."},
    "DUPLICATE_CODE": {"zh": "参与者编号已被使用。", "en": "This participant code is already in use."},
    "DUPLICATE_EMAIL": {"zh": "邮箱已被使用。", "en": "This email address is already in use."},
    "ALREADY_CHECKED_IN": {"zh": "该参与者已经签到。", "en": "This participant has already checked in."},
    "NOT_CHECKED_IN": {"zh": "请先为该参与者签到。", "en": "Check in this participant first."},
    "ALREADY_QUEUED": {"zh": "该参与者已经在队列中。", "en": "This participant is already in the queue."},
    "INVALID_STATE": {"zh": "参与者当前状态不允许此操作。", "en": "The participant’s current status does not allow this action."},
    "QUEUE_EMPTY": {"zh": "当前无人排队。", "en": "The queue is empty."},
    "STAGE_BUSY": {"zh": "已有参与者在台上。", "en": "A participant is already on stage."},
    "NOTHING_ON_STAGE": {"zh": "当前没有符合条件的上台者。", "en": "There is no matching participant on stage."},
    "INTERNAL_ERROR": {"zh": "服务暂时出错，请稍后再试。", "en": "An internal error occurred. Please try again later."},
}


def csv_row_message(code, fields, lang):
    if not fields:
        return messages[code][lang]
    reasons = {
        "required": {"zh": "必填", "en": "required"},
        "invalid": {"zh": "格式无效", "en": "invalid format"},
        "too_long": {"zh": "超过长度限制", "en": "too long"},
        "expected_three_columns": {"zh": "必须包含三列", "en": "expected three columns"},
    }
    return ", ".join(f"{field} ({reasons[reason][lang]})" for field, reason in fields.items())


def get_lang():
    for value in (request.headers.get("X-Lang"), request.cookies.get("lang")):
        if value in ("zh", "en"):
            return value
    return request.accept_languages.best_match(["zh", "en"], default="zh")
