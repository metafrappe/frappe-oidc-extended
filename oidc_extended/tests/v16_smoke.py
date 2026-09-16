"""Focused regressions for the v16 ports. External AI/AWS calls are simulated."""
import importlib
import io
import queue
import unittest
from types import SimpleNamespace
from unittest.mock import patch, Mock

import frappe
from frappe.model.base_document import get_controller


def run(app):
    assert app in frappe.get_installed_apps()
    modules = frappe.get_all('Module Def', filters={'app_name': app}, pluck='name')
    doctypes = frappe.get_all('DocType', filters={'module': ['in', modules]}, pluck='name')
    for doctype in doctypes:
        frappe.get_meta(doctype)
        get_controller(doctype)
    globals()['check_' + app]()
    print({'app': app, 'controllers': len(doctypes), 'regressions': 'passed'})


def check_oidc_extended():
    from oidc_extended.callback import custom
    from frappe.utils.oauth import create_oauth_state, consume_oauth_state
    with patch('oidc_extended.callback.get_info_via_oauth') as exchange, patch('frappe.respond_as_web_page') as response:
        custom('unused', 'unrecognized-state')
        exchange.assert_not_called()
        assert response.call_args.kwargs['http_status_code'] == 417
        state = create_oauth_state('/app')
        assert consume_oauth_state(state) == '/app'
        custom('unused', state)
        exchange.assert_not_called()
        assert response.call_args.kwargs['http_status_code'] == 417
    provider = frappe.get_doc({
        'doctype': 'Social Login Key', 'provider_name': 'V16 CI',
        'social_login_provider': 'Custom', 'client_id': 'ci', 'client_secret': 'ci',
        'base_url': 'https://idp.example.invalid', 'custom_base_url': 1,
        'authorize_url': '/authorize', 'access_token_url': '/token',
        'redirect_url': '/api/method/oidc_extended.callback.custom/v16_ci',
    }).insert()
    profile = frappe.get_doc({'doctype': 'Role Profile', 'role_profile': 'V16 OIDC Reader', 'roles': [{'role': 'Accounts User'}]}).insert()
    frappe.get_doc({'doctype': 'OIDC Extended Configuration', 'provider': provider.name,
                    'group_role_mappings': [{'group': 'accounting', 'role_profile': profile.name}]}).insert()
    token = create_oauth_state('/app')
    claims = {'sub': 'v16oidcuser', 'email': 'v16-oidc@example.invalid', 'email_verified': True,
              'given_name': 'OIDC', 'family_name': 'Reader', 'groups': ['accounting']}
    from werkzeug.test import EnvironBuilder
    from werkzeug.wrappers import Request
    previous_request = getattr(frappe.local, 'request', None)
    previous_manager = getattr(frappe.local, 'login_manager', None)
    manager = SimpleNamespace(user=None, post_login=Mock())
    try:
        frappe.local.request = Request(EnvironBuilder(path=provider.redirect_url).get_environ())
        frappe.local.login_manager = manager
        with patch('oidc_extended.callback.get_info_via_oauth', return_value=claims) as exchange:
            custom('ci-code', token)
            exchange.assert_called_once_with(provider.name, 'ci-code', id_token=True)
        user = frappe.get_doc('User', claims['email'])
        assert profile.name in [row.role_profile for row in user.role_profiles]
        assert 'Accounts User' in [row.role for row in user.roles]
        assert manager.user == user.name
        manager.post_login.assert_called_once()
        assert consume_oauth_state(token) is None
    finally:
        frappe.local.request = previous_request
        frappe.local.login_manager = previous_manager
