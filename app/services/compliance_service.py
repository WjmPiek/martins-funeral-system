import json
from datetime import datetime


def only_digits(value):
    return ''.join(ch for ch in str(value or '') if ch.isdigit())


def dob_from_sa_id(id_number):
    digits = only_digits(id_number)
    if len(digits) < 6:
        return ''
    yy = int(digits[:2])
    mm = digits[2:4]
    dd = digits[4:6]
    current_yy = datetime.now().year % 100
    century = 1900 if yy > current_yy else 2000
    try:
        datetime(century + yy, int(mm), int(dd))
    except ValueError:
        return ''
    return f'{dd}/{mm}/{century + yy}'


def format_dob(value):
    raw = str(value or '').strip()
    digits = only_digits(raw)
    if len(digits) == 13:
        return dob_from_sa_id(digits)
    if len(digits) == 6:
        return dob_from_sa_id(digits)
    if len(digits) == 8:
        # Accept DDMMYYYY or YYYYMMDD.
        if 1900 <= int(digits[:4]) <= datetime.now().year:
            yyyy, mm, dd = digits[:4], digits[4:6], digits[6:8]
        else:
            dd, mm, yyyy = digits[:2], digits[2:4], digits[4:8]
        try:
            datetime(int(yyyy), int(mm), int(dd))
            return f'{dd}/{mm}/{yyyy}'
        except ValueError:
            return raw
    return raw


def is_valid_sa_id(id_number):
    digits = only_digits(id_number)
    if len(digits) != 13 or not dob_from_sa_id(digits):
        return False
    odd_sum = sum(int(digits[i]) for i in range(0, 12, 2))
    even_concat = ''.join(digits[i] for i in range(1, 12, 2))
    even_sum = sum(int(ch) for ch in str(int(even_concat) * 2)) if even_concat else 0
    check = (10 - ((odd_sum + even_sum) % 10)) % 10
    return check == int(digits[-1])


def age_from_dob(value):
    dob = format_dob(value)
    digits = only_digits(dob)
    if len(digits) != 8:
        return None
    dd, mm, yyyy = int(digits[:2]), int(digits[2:4]), int(digits[4:8])
    try:
        born = datetime(yyyy, mm, dd).date()
    except ValueError:
        return None
    today = datetime.now().date()
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


def is_debit_order(payment_method):
    return 'debit' in str(payment_method or '').lower()


def product_text(product):
    if not product:
        return ''
    return f'{getattr(product,"product_name","") or ""} {getattr(product,"plan_name","") or ""}'.lower()


def classify_product_template(product):
    text = product_text(product)
    if 'member +' in text or 'member+' in text or ('product' in text and ('+' in text or 'member' in text)):
        return 'member_product'
    return 'single_family'


def _rows(value):
    if not value:
        return []
    try:
        data = json.loads(value)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def validate_age_limit(label, dob_value, product, errors):
    age = age_from_dob(dob_value)
    if age is None:
        return
    min_age = getattr(product, 'min_age', None) if product else None
    max_age = getattr(product, 'max_age', None) if product else None
    if min_age is not None and age < int(min_age):
        errors.append(f'{label} age is {age}. Minimum age for this policy is {min_age}.')
    if max_age is not None and age > int(max_age):
        errors.append(f'{label} age is {age}. Maximum age for this policy is {max_age}.')


def validate_application_rules(app_obj):
    errors = []
    product = getattr(app_obj, 'product', None)
    method = getattr(app_obj, 'payment_method', '')

    if not product:
        errors.append('Please select a valid policy/product.')

    id_number = getattr(app_obj, 'id_number', '')
    if not id_number:
        errors.append('Principal member ID number is required for FICA.')
    elif not is_valid_sa_id(id_number):
        errors.append('Principal member ID number failed South African ID validation.')

    stored_dob = format_dob(getattr(app_obj, 'date_of_birth', '') or dob_from_sa_id(id_number))
    id_dob = dob_from_sa_id(id_number)
    if id_dob and stored_dob and stored_dob != id_dob:
        errors.append('Principal member DOB does not match the South African ID number.')

    validate_age_limit('Principal member', stored_dob, product, errors)

    spouse_id = getattr(app_obj, 'spouse_id_number', '')
    spouse_dob = format_dob(getattr(app_obj, 'spouse_date_of_birth', '') or dob_from_sa_id(spouse_id))
    if spouse_id and not is_valid_sa_id(spouse_id):
        errors.append('Spouse ID number failed South African ID validation.')
    if spouse_dob:
        validate_age_limit('Spouse', spouse_dob, product, errors)

    for label, rows in [('Dependent', _rows(getattr(app_obj, 'dependents_json', ''))), ('Extended family member', _rows(getattr(app_obj, 'extended_family_json', ''))), ('Product dependent', _rows(getattr(app_obj, 'product_dependents_json', '')) )]:
        for idx, row in enumerate(rows, start=1):
            id_or_dob = row.get('id_or_dob') or row.get('id_number') or row.get('date_of_birth')
            digits = only_digits(id_or_dob)
            if len(digits) == 13 and not is_valid_sa_id(digits):
                errors.append(f'{label} {idx} ID number failed South African ID validation.')
            validate_age_limit(f'{label} {idx}', dob_from_sa_id(id_or_dob) or id_or_dob, product, errors)

    if is_debit_order(method):
        required_bank = [
            ('Bank Name', getattr(app_obj, 'bank_name', '')),
            ('Branch Code', getattr(app_obj, 'branch_code', '')),
            ('Account Number', getattr(app_obj, 'account_number', '')),
            ('Account Type', getattr(app_obj, 'account_type', '')),
            ('Account Holder', getattr(app_obj, 'account_holder', '')),
        ]
        for label, value in required_bank:
            if not str(value or '').strip():
                errors.append(f'{label} is required because payment method is Debit Order.')
    return errors


def assert_application_rules(app_obj):
    errors = validate_application_rules(app_obj)
    return (len(errors) == 0, errors)
