# Part of Odoo. See LICENSE file for full copyright and licensing details.

def get_clean_email(email):
    """Quita caracteres invisibles o no ASCII del correo electrónico."""
    if not email:
        return ''
    return email.encode('ascii', 'ignore').decode('utf-8')


def get_partner_email(partner):
    """Obtiene un correo válido desde el partner."""
    return get_clean_email(partner.email or '')


def get_partner_metadata(partner):
    """Devuelve metadata adicional útil para Culqi."""
    return {
        'document_number': partner.vat or '',
        'full_name': partner.name or '',
    }
