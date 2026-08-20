from app.update_manager import version_key

def test_version_key():
    assert version_key('v1.6.0') > version_key('1.5.9')
    assert version_key('1.5.0') == (1,5,0)
