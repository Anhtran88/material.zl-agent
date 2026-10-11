"""Evidence-backed M4 text extraction. No inferred delivery confirmation/accounting."""
import re
import hashlib
from datetime import date
from decimal import Decimal

VERSION = 'm4-text-v1'
DATES = re.compile(r'(?<!\d)(\d{1,2})/(\d{1,2})/(\d{4})(?!\d)')
QUANTITIES = re.compile(r'(?<![\w.,])(?P<number>\d+(?:[.,]\d+)*)(?P<space>\s*)(?P<unit>m³|m3|tấn|tạ|kg|bao|viên|ống|đinh|demi|tấm|mét|lít)(?!\w)', re.I)
MATERIAL = re.compile(r'\b(xi\s+măng|bê\s+tông|đá\s+\d+x\d+|đá|cát|gạch|thép|sắt)\b', re.I)
PROJECT = re.compile(r'công\s+trình\s*:?\s*([^\n(;]+)', re.I)


def evidence(text, match, value):
    return {'value':value, 'raw':text[match.start():match.end()],
            'span':[match.start(),match.end()], 'basis':'message_text'}


def number_value(raw):
    # Vietnamese comma decimals and dotted groups. Ambiguous dotted decimals stay unknown.
    if ',' in raw:
        if raw.count(',') != 1: return None
        integer, fraction = raw.split(',')
        if '.' in integer and not re.fullmatch(r'\d{1,3}(?:\.\d{3})+', integer): return None
        value = integer.replace('.','') + '.' + fraction
    elif '.' in raw:
        if not re.fullmatch(r'\d{1,3}(?:\.\d{3})+',raw): return None
        value = raw.replace('.','')
    else: value = raw
    return format(Decimal(value), 'f')


def extract_message(message, source):
    text=message['text']
    identifier=message['domContainerId']
    dates=[]
    for match in DATES.finditer(text):
        try: value=date(int(match[3]),int(match[2]),int(match[1])).isoformat()
        except ValueError: value=None
        dates.append(evidence(text,match,value))
    quantities=[]
    for match in QUANTITIES.finditer(text):
        item=evidence(text,match,number_value(match['number']))
        item['unit']=match['unit'].lower().replace('m³','m3')
        quantities.append(item)
    materials=[evidence(text,m,m[0]) for m in MATERIAL.finditer(text)]
    projects=[]
    for match in PROJECT.finditer(text):
        label=match[1].strip()
        quantity=QUANTITIES.search(label)
        if quantity: label=label[:quantity.start()].rstrip(' :,-')
        projects.append(evidence(text,match,label or None))
    missing=[]
    for name, values in [('messageDate',dates),('material',materials),('project',projects),('quantities',quantities)]:
        if not values: missing.append(name)
    if len({x['value'] for x in dates}) > 1: missing.append('multiple_message_dates')
    if any(x['value'] is None for x in dates+quantities+projects): missing.append('invalid_or_ambiguous_value')
    return {'extractionId':hashlib.sha256((VERSION+'\0'+source+'\0'+identifier+'\0'+text).encode()).hexdigest(),
            'sourceId':source, 'domContainerId':identifier, 'originalText':text,
            'messageDates':dates, 'materials':materials, 'projects':projects, 'quantities':quantities,
            'slipConfirmationDate':None, 'slipDateStatus':'NOT_READ',
            'missingFields':missing, 'status':'NEEDS_REVIEW' if missing else 'TEXT_EXTRACTED',
            'accountingActive':False}


def extract_report(report):
    return {'schemaVersion':1,'rulesetVersion':VERSION,'rows':[
        extract_message(message,report['candidateSourceId']) for message in report.get('messages',[])],
        'slipOcrImplemented':False,'accountingActive':False}
