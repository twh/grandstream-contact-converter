#!/usr/bin/env python3
# Convert VCF (vCard) files to Grandstream XML phonebook format.
# Usage: python vcf_to_grandstream.py input.vcf [output.xml]

import sys
import re
from html import escape

def convert_letters_to_digits(phone_str):
    # Convert letters to digits based on phone keypad mapping
    keypad_map = {
        'A': '2', 'B': '2', 'C': '2',
        'D': '3', 'E': '3', 'F': '3',
        'G': '4', 'H': '4', 'I': '4',
        'J': '5', 'K': '5', 'L': '5',
        'M': '6', 'N': '6', 'O': '6',
        'P': '7', 'Q': '7', 'R': '7', 'S': '7',
        'T': '8', 'U': '8', 'V': '8',
        'W': '9', 'X': '9', 'Y': '9', 'Z': '9'
    }
    
    result = ""
    for char in phone_str.upper():
        if char in keypad_map:
            result += keypad_map[char]
        else:
            result += char
    
    return result

def sanitize_phone_number(phone_str):
    # Convert letters to digits, then remove non-DTMF characters, keeping only digits, +, *, #
    # First convert letters to digits
    converted = convert_letters_to_digits(phone_str)
    # Then remove non-DTMF characters
    sanitized = re.sub(r'[^\+\*#0-9]', '', converted)
    return sanitized

def count_digits(phone_str):
    # Count only the actual digits in a phone number (exclude + symbol)
    return len(re.sub(r'[^0-9]', '', phone_str))

def map_phone_type(vcard_type):
    # Map vCard phone types to Grandstream types
    # Grandstream only has three types
    type_mapping = {
        'work': 'Work',
        'home': 'Home',
        'cell': 'Mobile',
        'mobile': 'Mobile',
        'main': 'Work',
        'phone': 'Work',
        'other': 'Work',
        'voice': 'Work',
        'fax': 'Work',
        'pager': 'Work'
    }
    
    vcard_type_lower = vcard_type.lower()
    return type_mapping.get(vcard_type_lower, 'Work')

def parse_vcard_line(line):
    # Parse a single vCard line into property, parameters, and value
    line = line.strip()
    if not line:
        return None, None, None
    
    # Split on first colon to separate property from value
    if ':' not in line:
        return None, None, None
    
    prop_part, value = line.split(':', 1)
    
    # Parse property and parameters
    if ';' in prop_part:
        parts = prop_part.split(';')
        prop_name = parts[0]
        
        # Collect all type parameters
        params = {}
        type_values = []
        
        for param in parts[1:]:
            if '=' in param:
                key, val = param.split('=', 1)
                if key.upper() == 'TYPE':
                    type_values.append(val.upper())
                else:
                    params[key.upper()] = val.upper()
            else:
                # Handle bare parameters like PREF
                params[param.upper()] = True
        
        # Store all type values
        if type_values:
            params['TYPE'] = type_values
    else:
        prop_name = prop_part
        params = {}
    
    return prop_name.upper(), params, value

def parse_vcf_file(vcf_content):
    # Parse VCF file content and return list of contacts
    contacts = []
    current_contact = {}
    
    lines = vcf_content.split('\n')
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # Handle line folding (lines starting with space or tab)
        if line.startswith(' ') or line.startswith('\t'):
            # This is a continuation of the previous line
            continue
        
        prop_name, params, value = parse_vcard_line(line)
        
        if prop_name == 'BEGIN' and value == 'VCARD':
            current_contact = {}
        elif prop_name == 'END' and value == 'VCARD':
            if current_contact:
                contacts.append(current_contact)
                current_contact = {}
        elif prop_name:
            if prop_name not in current_contact:
                current_contact[prop_name] = []
            current_contact[prop_name].append({
                'value': value,
                'params': params
            })
    
    return contacts

def extract_contact_info(contact):
    #Extract name and phone information from a contact#
    firstname = ""
    lastname = ""
    
    # Extract name from N property (structured name)
    if 'N' in contact:
        n_value = contact['N'][0]['value']
        # N property format: Family;Given;Additional;Prefix;Suffix
        name_parts = n_value.split(';')
        if len(name_parts) >= 2:
            lastname = name_parts[0].strip()
            firstname = name_parts[1].strip()
    
    # If no structured name, try full name (FN)
    if not firstname and 'FN' in contact:
        firstname = contact['FN'][0]['value'].strip()
    
    # Extract and process phone numbers - take first 3 valid numbers
    phone_numbers = []
    
    if 'TEL' in contact:
        for tel in contact['TEL']:
            # Stop if we already have 3 numbers
            if len(phone_numbers) >= 3:
                break
                
            phone_value = tel['value'].strip()
            sanitized_phone = sanitize_phone_number(phone_value)
            
            # Only include numbers with more than 6 digits (filters out SMS short codes)
            if sanitized_phone and count_digits(sanitized_phone) > 6:
                phone_type = 'Work'  # Default for ALL unknown/unmatched types
                
                if 'TYPE' in tel['params']:
                    # TYPE parameter is now a list of values
                    type_values = tel['params']['TYPE']
                    if isinstance(type_values, list):
                        # Look for the main type (CELL/MOBILE, HOME, WORK)
                        # All other types (MAIN, FAX, PAGER, VOICE, etc.) will remain as 'Work'
                        for type_val in type_values:
                            type_val_lower = type_val.lower()
                            if type_val_lower in ['cell', 'mobile']:
                                phone_type = 'Mobile'
                                break
                            elif type_val_lower == 'home':
                                phone_type = 'Home'
                                break
                            elif type_val_lower == 'work':
                                phone_type = 'Work'
                                break
                        # Note: types like 'main', 'fax', 'pager', 'voice', 'iphone', etc. 
                        # will keep the default 'Work' assignment
                    else:
                        # Single type value (fallback)
                        type_val_lower = type_values.lower()
                        if type_val_lower in ['cell', 'mobile']:
                            phone_type = 'Mobile'
                        elif type_val_lower == 'home':
                            phone_type = 'Home'
                        elif type_val_lower == 'work':
                            phone_type = 'Work'
                        # All other single types default to 'Work'
                
                phone_numbers.append((phone_type, sanitized_phone))
    
    return firstname, lastname, phone_numbers

def generate_contact_xml(contact_id, firstname, lastname, phone_numbers):
    #Generate XML for a single contact#
    if not firstname or not phone_numbers:
        return None
    
    xml_parts = []
    xml_parts.append('<Contact>')
    xml_parts.append(f'<id>{contact_id}</id>')
    xml_parts.append(f'<FirstName>{escape(firstname)}</FirstName>')
    
    if lastname:
        xml_parts.append(f'<LastName>{escape(lastname)}</LastName>')
    
    for phone_type, phone_number in phone_numbers:
        xml_parts.append(f'<Phone type="{phone_type}">')
        xml_parts.append(f'<phonenumber>{escape(phone_number)}</phonenumber>')
        xml_parts.append('<accountindex>1</accountindex>')
        xml_parts.append('</Phone>')
    
    xml_parts.append('<Frequent>0</Frequent>')
    xml_parts.append('<Primary>0</Primary>')
    xml_parts.append('</Contact>')
    
    return '\n'.join(xml_parts)

def convert_vcf_to_xml(vcf_file, xml_file):
    # Convert VCF file to Grandstream XML format
    try:
        with open(vcf_file, 'r', encoding='utf-8') as f:
            vcf_content = f.read()
        
        # Parse VCF file
        contacts = parse_vcf_file(vcf_content)
        
        # Start XML output
        xml_output = []
        xml_output.append('<?xml version="1.0" encoding="UTF-8"?>')
        xml_output.append('<AddressBook>')
        
        contact_id = 1
        processed_contacts = 0
        
        for contact in contacts:
            firstname, lastname, phone_numbers = extract_contact_info(contact)
            contact_xml = generate_contact_xml(contact_id, firstname, lastname, phone_numbers)
            
            if contact_xml:
                xml_output.append(contact_xml)
                contact_id += 1
                processed_contacts += 1
        
        xml_output.append('</AddressBook>')
        
        # Write XML file
        with open(xml_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(xml_output))
        
        print(f"Successfully converted {processed_contacts} contacts from {vcf_file} to {xml_file}")
        
    except FileNotFoundError:
        print(f"Error: File '{vcf_file}' not found.")
        sys.exit(1)
    except Exception as e:
        print(f"Error processing file: {e}")
        sys.exit(1)

def main():
    if len(sys.argv) < 2:
        print("Usage: python vcf_to_grandstream.py input.vcf [output.xml]")
        sys.exit(1)
    
    vcf_file = sys.argv[1]
    xml_file = sys.argv[2] if len(sys.argv) > 2 else vcf_file.rsplit('.', 1)[0] + '.xml'
    
    convert_vcf_to_xml(vcf_file, xml_file)

if __name__ == "__main__":
    main()
