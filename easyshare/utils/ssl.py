import ssl
import tempfile
from typing import Dict, Optional

from easyshare import logging
from easyshare.logging import get_logger
from easyshare.utils.json import json_to_pretty_str

log = get_logger(__name__)
log.setLevel(logging.LEVEL_DEBUG)


def parse_cert(cert: bytes) -> Optional[Dict]:
    log.d("Encrypted binary cert\n%s", cert)
    # print("Encrypted binary cert\n", cert)

    cert_enc_str = ssl.DER_cert_to_PEM_cert(cert)

    log.d("Encrypted plain cert\n%s", cert_enc_str)
    # print("Encrypted plain cert\n", cert_enc_str)

    cert_dec = None

    with tempfile.NamedTemporaryFile(mode="w") as tmpf:
        tmpf.write(cert_enc_str)
        tmpf.flush()

        cert_dec = ssl._ssl._test_decode_cert(tmpf.name)
        log.d("Decrypted cert\n%s", json_to_pretty_str(cert_dec))
        # print("Decrypted cert\n", json_to_pretty_str(cert_dec))

    return cert_dec
