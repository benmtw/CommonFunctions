from common_functions import (
    get_disposable_domains,
    get_free_provider_domains,
    is_disposable_email,
    is_free_provider_email,
    is_personalized_email,
)


def test_personalized_email_true():
    assert is_personalized_email("john.smith@company.co.uk")
    assert is_personalized_email("sarah+newsletter@company.com")


def test_personalized_email_false_for_role_accounts():
    assert not is_personalized_email("info@company.com")
    assert not is_personalized_email("support-eu@company.com")


def test_personalized_email_false_for_invalid_or_numeric_local_part():
    assert not is_personalized_email("not-an-email")
    assert not is_personalized_email("12345@company.com")


def test_free_provider_detection():
    assert is_free_provider_email("person@gmail.com")
    assert is_free_provider_email("person@mail.gmx.com")
    assert not is_free_provider_email("person@company.com")


def test_disposable_provider_detection():
    assert is_disposable_email("test@mailinator.com")
    assert is_disposable_email("test@inbox.sharklasers.com")
    assert not is_disposable_email("test@gmail.com")


def test_domain_loaders_include_packaged_data():
    free = get_free_provider_domains()
    disposable = get_disposable_domains()
    assert "gmx.com" in free
    assert "sharklasers.com" in disposable
