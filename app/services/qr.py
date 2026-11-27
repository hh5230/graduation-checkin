from io import BytesIO

import qrcode


def qr_png(token):
    qr = qrcode.QRCode(box_size=10, border=2)
    qr.add_data("GRAD:" + token)
    output = BytesIO()
    qr.make_image().save(output, format="PNG")
    return output.getvalue()
