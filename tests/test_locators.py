from easyshare.es.common import ServerLocation, SharingLocation


def test_server_location():
    assert ServerLocation.parse("hostname").name == "hostname"
    assert ServerLocation.parse("192.168.1.105").ip == "192.168.1.105"
    assert ServerLocation.parse("192.168.1.105:8888").port == 8888


def test_sharing_location():
    assert SharingLocation.parse("shared").name == "shared"
    assert not SharingLocation.parse("shared").server_ip

    assert SharingLocation.parse("shared@192.168.1.105").server_ip == "192.168.1.105"
    assert SharingLocation.parse("shared@192.168.1.105:9999").server_port == 9999
    assert SharingLocation.parse("shared@john-arch").server_name == "john-arch"
    assert not SharingLocation.parse("shared@john-arch").server_ip

    assert SharingLocation.parse("shared@192.168.1.105/Music").path == "Music"
    assert SharingLocation.parse("shared@192.168.1.105:9999/Music").path == "Music"
    assert SharingLocation.parse("shared/Music").path == "Music"
    assert SharingLocation.parse("shared//Music").path == "/Music"


