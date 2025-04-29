#!/usr/bin/env python3
"""
Form Data Manager for the Extension Crawler
Provides smart form filling with context-awareness
"""

import json
import logging
import os
import random
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)

class FormDataManager:
    """
    Advanced form data manager with context-awareness and regional support
    """
    
    # Default form values for India
    INDIA_FORM_VALUES = {
        # Personal information
        'name': ['Raj Kumar', 'Priya Sharma', 'Amit Patel', 'Shreya Singh', 'Mohammed Khan', 
                 'Ananya Reddy', 'Vikram Gupta', 'Deepika Iyer', 'Sanjay Desai', 'Kavita Nair'],
        'first_name': ['Raj', 'Priya', 'Amit', 'Shreya', 'Mohammed', 'Ananya', 'Vikram', 'Deepika', 'Sanjay', 'Kavita'],
        'last_name': ['Kumar', 'Sharma', 'Patel', 'Singh', 'Khan', 'Reddy', 'Gupta', 'Iyer', 'Desai', 'Nair'],
        'email': ['rajeev.kumar@example.com', 'priya.s@gmail.com', 'amit2023@yahoo.com', 'shreya_singh@outlook.com'],
        'phone': ['+91 9876543210', '+91 8765432109', '+91 7654321098', '9876543210', '08765432109'],
        'gender': ['Male', 'Female', 'Other'],
        'date_format': ['DD/MM/YYYY', 'DD-MM-YYYY'],

        # ID Documents (formatted)
        'aadhaar': ['1234 5678 9012', '2345 6789 0123', '3456 7890 1234'],
        'pan': ['ABCDE1234F', 'FGHIJ5678K', 'KLMNO9012P'],
        'voter_id': ['ABC1234567', 'XYZ9876543', 'LMN5432109'],
        'passport': ['A1234567', 'M9876543', 'Z5432109'],
        'driving_license': ['DL-0123456789', 'MH0987654321', 'KA5432109876'],
        'gst': ['27AAPFU0939F1ZV', '29AABCP9621L1ZP', '33AAACR4849R1ZO', '06AABCF8381G1ZT'],
        'electricity_consumer_no': ['123456789', '987654321', '567891234'],
        'gas_consumer_no': ['1234567890', '9876543210', '5678912345'],
        'vehicle_reg_no': ['MH01AB1234', 'DL01RT5678', 'KA02MN9012'],
        
        # Address components
        'address': [
            '123 MG Road', '45 Nehru Street', '78 Gandhi Nagar', 
            'Flat 101, Sunrise Apartments', '56/B, Lake View Colony',
            'H.No. 123, Sector 15', 'Plot No. 45, Phase 2', 'Door No. 12-3-456/A',
            'Villa 23, Palm Grove', '143, Civil Lines', '234, Malviya Nagar',
            'Shop No. 5, City Center Mall'
        ],
        'address_line2': [
            'Near City Hospital', 'Behind Central Mall', 'Opp. Railway Station',
            '2nd Floor', 'Sector 15', 'Old Bus Stand Road', 'Near Metro Station',
            'Shastri Nagar', 'Vasant Kunj', 'Defence Colony', 'Jubilee Hills',
            'Salt Lake', 'Lavelle Road', 'M.G. Road', 'P.O. Box 12345'
        ],
        'landmark': [
            'Near Axis Bank', 'Opposite Metro Station', 'Behind Central Park',
            'Next to Apollo Hospital', 'Near IIT Campus', 'Beside State Bank',
            'Across from Reliance Fresh', 'Next to Big Bazaar', 'Near PVR Cinema',
            'Between SBI and HDFC Bank', 'Opposite Dmart', 'Adjacent to Post Office'
        ],
        'city': [
            'Mumbai', 'Delhi', 'Bangalore', 'Hyderabad', 'Chennai', 
            'Kolkata', 'Pune', 'Ahmedabad', 'Jaipur', 'Lucknow'
        ],
        'state': [
            'Maharashtra', 'Delhi', 'Karnataka', 'Telangana', 'Tamil Nadu',
            'West Bengal', 'Gujarat', 'Rajasthan', 'Uttar Pradesh', 'Kerala'
        ],
        'state_code': [
            'MH', 'DL', 'KA', 'TS', 'TN', 'WB', 'GJ', 'RJ', 'UP', 'KL'
        ],
        'pincode': [
            '400001', '110001', '560001', '500001', '600001',
            '700001', '411001', '380001', '302001', '226001'
        ],
        'country': ['India', 'भारत'],
        'country_code': ['IN'],
        
        # Payment information
        'currency': ['INR', '₹'],
        'credit_card': ['4111 1111 1111 1111', '5555 5555 5555 4444', '3782 822463 10005'],
        'credit_card_expiry': ['12/25', '06/24', '09/26', '03/23'],
        'credit_card_cvv': ['123', '456', '789'],
        'upi_id': ['username@ybl', 'user@okicici', 'mobile@paytm', 'name@upi'],
        'bank_account': ['123456789012', '234567890123', '345678901234'],
        'ifsc_code': ['SBIN0001234', 'HDFC0001234', 'ICIC0001234'],
        
        # Common form inputs
        'username': ['rajkumar89', 'priya_s', 'amit2023', 'shreya_singh'],
        'password': ['SecurePass@123', 'India2023#', 'MyP@ssw0rd!', 'Str0ng!Pass'],
     'search_term': ['best smartphone', 'restaurants near me', 'cheap flights', 'online courses', "laptop", 
                        "table", "bottle", "chair", "shoe", "backpack", "pen", "camera", "phone", "headphones", 
                        "wallet", "book", "lamp", "bed", "sofa", "television", "bicycle", "car", "burger", "pizza",
                        # Electronics
                        "smartwatch", "tablet", "gaming console", "wireless earbuds", "smart speaker", "printer", "monitor",
                        # Home & Living
                        "coffee maker", "microwave", "refrigerator", "washing machine", "air conditioner", "vacuum cleaner",
                        # Fashion
                        "t-shirt", "jeans", "dress", "jacket", "sneakers", "sunglasses", "watch", "handbag", "belt",
                        # Food & Beverages
                        "coffee", "tea", "sandwich", "salad", "sushi", "pasta", "ice cream", "chocolate", "juice",
                        # Services
                        "hair salon", "gym membership", "car repair", "house cleaning", "plumber", "electrician",
                        # Entertainment
                        "movie tickets", "concert tickets", "video games", "board games", "streaming services",
                        # Travel
                        "hotel booking", "car rental", "vacation packages", "travel insurance", "tourist attractions",
                        # Education
                        "language courses", "coding bootcamp", "music lessons", "art classes", "tutoring services",
                        # Health & Wellness
                        "vitamins", "yoga mat", "fitness tracker", "face mask", "hand sanitizer", "first aid kit"],
        'url': ['https://www.example.com', 'https://example.co.in'],
        'comment': [
            'This is a great product!', 
            'Looking forward to your response', 
            'Please provide more information',
            'Thank you for your service'
        ],
        'default_text': ['Sample text', 'Test input', 'Example data', 'Form field value'],
        
        # Date components (for generated dates)
        'days': list(range(1, 32)),
        'months': list(range(1, 13)),
        'years': list(range(1950, 2005)),
        'recent_years': list(range(2010, 2023)),
        
        # Education
        'education': ['Bachelor of Engineering', 'Bachelor of Arts', 'Bachelor of Science', 
                     'Master of Technology', 'Master of Business Administration', 'PhD'],
        'university': ['Delhi University', 'Mumbai University', 'IIT Bombay', 'IIT Delhi', 
                      'Bangalore University', 'Anna University'],
                      
        # Occupation
        'occupation': ['Software Engineer', 'Teacher', 'Doctor', 'Business Analyst', 
                      'Accountant', 'Student', 'Marketing Manager'],
                      
        # Language options
        'language': ['English', 'Hindi', 'Tamil', 'Telugu', 'Bengali', 'Marathi', 'Gujarati'],
        
        # Other common fields
        'age': ['25', '30', '35', '42', '28', '33'],
        'income_range': ['Below 5 Lakhs', '5-10 Lakhs', '10-15 Lakhs', 'Above 15 Lakhs'],
        'marital_status': ['Single', 'Married', 'Divorced', 'Widowed'],
    }
    
    # Default form values for USA
    USA_FORM_VALUES = {
        # Personal information
        'name': ['John Smith', 'Michael Johnson', 'Sarah Williams', 'Jennifer Davis', 'David Wilson', 
                'Lisa Anderson', 'Robert Martinez', 'Emily Taylor', 'Thomas Brown', 'Jessica Miller'],
        'first_name': ['John', 'Michael', 'Sarah', 'Jennifer', 'David', 'Lisa', 'Robert', 'Emily', 'Thomas', 'Jessica'],
        'last_name': ['Smith', 'Johnson', 'Williams', 'Davis', 'Wilson', 'Anderson', 'Martinez', 'Taylor', 'Brown', 'Miller'],
        'email': ['john.smith@example.com', 'sarah.w@gmail.com', 'michael2023@yahoo.com', 'jenny_davis@outlook.com'],
        'phone': ['+1 (555) 123-4567', '+1 (555) 987-6543', '(555) 234-5678', '555-876-5432', '5554567890'],
        'gender': ['Male', 'Female', 'Other', 'Prefer not to say'],
        'date_format': ['MM/DD/YYYY', 'MM-DD-YYYY'],

        # ID Documents (formatted)
        'ssn': ['123-45-6789', '234-56-7890', '345-67-8901', '456-78-9012'],
        'passport': ['123456789', '987654321', 'AB1234567'],
        'driving_license': ['D1234567', 'F987654321', 'S12345678', 'DL5432109'],
        'state_id': ['I1234567', 'ID987654', 'S12345ID'],
        'medicare': ['1234-567-8901', '5678-901-2345'],
        'ein': ['12-3456789', '98-7654321'],
        'vehicle_reg_no': ['ABC1234', 'XYZ9876', '123-ABC', 'CA-987XYZ'],
        
        # Address components
        'address': [
            '123 Main Street', '456 Oak Avenue', '789 Maple Drive', 
            'Apt 101, Sunset Apartments', '567 Pine Court',
            '222 Broadway', '1500 Park Avenue', '750 5th Street',
            '888 Ocean Boulevard', '345 Washington Street', '432 Lincoln Road',
            'Suite 500, Century Building'
        ],
        'address_line2': [
            'Apartment 2B', 'Suite 300', 'Unit 45', 
            '2nd Floor', 'Building C', 'Room 789', 'Apt #12',
            'Basement', 'Penthouse', 'Rear Entrance', 'Front Desk',
            'P.O. Box 12345', 'Box 678', 'Mail Stop MS-123'
        ],
        'landmark': [
            'Near City Park', 'Across from Walmart', 'Behind Public Library',
            'Next to General Hospital', 'Near State University', 'Beside Chase Bank',
            'Across from McDonalds', 'Next to Target', 'Near AMC Theater',
            'Between Bank of America and CVS', 'Opposite Starbucks', 'Adjacent to Post Office'
        ],
        'city': [
            'New York', 'Los Angeles', 'Chicago', 'Houston', 'Phoenix', 
            'Philadelphia', 'San Antonio', 'San Diego', 'Dallas', 'San Jose'
        ],
        'state': [
            'New York', 'California', 'Illinois', 'Texas', 'Arizona',
            'Pennsylvania', 'Texas', 'California', 'Texas', 'California'
        ],
        'state_code': [
            'NY', 'CA', 'IL', 'TX', 'AZ', 'PA', 'TX', 'CA', 'TX', 'CA'
        ],
        'zipcode': [
            '10001', '90001', '60601', '77001', '85001',
            '19101', '78201', '92101', '75201', '95101'
        ],
        'country': ['United States', 'USA', 'US', 'U.S.A.'],
        'country_code': ['US'],
        
        # Payment information
        'currency': ['USD', '$'],
        'credit_card': ['4111 1111 1111 1111', '5555 5555 5555 4444', '3782 822463 10005', '6011 0000 0000 0004'],
        'credit_card_expiry': ['12/25', '06/24', '09/26', '03/23'],
        'credit_card_cvv': ['123', '456', '789'],
        'routing_number': ['021000021', '011401533', '091000019'],
        'bank_account': ['12345678901234', '98765432109876', '45678901234567'],
        'bank_name': ['Chase', 'Bank of America', 'Wells Fargo', 'Citibank', 'Capital One'],
        
        # Common form inputs
        'username': ['johnsmith', 'sarah_w', 'michael2023', 'jenny.davis'],
        'password': ['SecurePass@123', 'America2023#', 'MyP@ssw0rd!', 'Str0ng!Pass'],
        'search_term': ['best smartphone', 'restaurants near me', 'cheap flights', 'online courses', "laptop", 
                        "table", "bottle", "chair", "shoe", "backpack", "pen", "camera", "phone", "headphones", 
                        "wallet", "book", "lamp", "bed", "sofa", "television", "bicycle", "car", "burger", "pizza",
                        # Electronics
                        "smartwatch", "tablet", "gaming console", "wireless earbuds", "smart speaker", "printer", "monitor",
                        # Home & Living
                        "coffee maker", "microwave", "refrigerator", "washing machine", "air conditioner", "vacuum cleaner",
                        # Fashion
                        "t-shirt", "jeans", "dress", "jacket", "sneakers", "sunglasses", "watch", "handbag", "belt",
                        # Food & Beverages
                        "coffee", "tea", "sandwich", "salad", "sushi", "pasta", "ice cream", "chocolate", "juice",
                        # Services
                        "hair salon", "gym membership", "car repair", "house cleaning", "plumber", "electrician",
                        # Entertainment
                        "movie tickets", "concert tickets", "video games", "board games", "streaming services",
                        # Travel
                        "hotel booking", "car rental", "vacation packages", "travel insurance", "tourist attractions",
                        # Education
                        "language courses", "coding bootcamp", "music lessons", "art classes", "tutoring services",
                        # Health & Wellness
                        "vitamins", "yoga mat", "fitness tracker", "face mask", "hand sanitizer", "first aid kit"],
        'url': ['https://www.example.com', 'https://example.com'],
        'comment': [
            'Great product, would recommend!', 
            'Looking forward to hearing from you', 
            'Please provide additional information',
            'Thank you for your excellent service'
        ],
        'default_text': ['Sample text', 'Test input', 'Example data', 'Form field value'],
        
        # Date components (for generated dates)
        'days': list(range(1, 32)),
        'months': list(range(1, 13)),
        'years': list(range(1950, 2005)),
        'recent_years': list(range(2010, 2023)),
        
        # Education
        'education': ['Bachelor of Arts', 'Bachelor of Science', 'Master of Arts', 'Master of Science', 
                     'Master of Business Administration', 'PhD', 'High School Diploma', 'Associate Degree'],
        'university': ['Harvard University', 'Stanford University', 'MIT', 'University of California', 
                      'New York University', 'University of Texas', 'University of Michigan'],
                      
        # Occupation
        'occupation': ['Software Engineer', 'Teacher', 'Doctor', 'Business Analyst', 
                      'Accountant', 'Student', 'Marketing Manager', 'Nurse', 'Sales Representative'],
                      
        # Language options
        'language': ['English', 'Spanish', 'French', 'German', 'Chinese', 'Japanese', 'Arabic'],
        
        # Other common fields
        'age': ['25', '30', '35', '42', '28', '33'],
        'income_range': ['Under $25,000', '$25,000-$50,000', '$50,000-$100,000', 'Over $100,000'],
        'marital_status': ['Single', 'Married', 'Divorced', 'Widowed', 'Separated'],
    }
    
    # Address field patterns for more accurate detection
    ADDRESS_PATTERNS = {
        'address_line1': [
            'address', 'street', 'addr', 'address line 1', 'address1', 'addressline1', 
            'location', 'residence', 'house', 'flat', 'apartment', 'building', 'home',
            'address_line_1', 'addressline 1', 'address line one', 'delivery address',
            'shipping address', 'billing address', 'mailing address', 'street address',
            'current address', 'permanent address', 'residential address', 'room',
            'property', 'house no', 'plot', 'villa', 'door no', 'door', 'lane', 'road'
        ],
        'address_line2': [
            'address line 2', 'address2', 'addr2', 'addressline2', 'apt', 'suite', 'unit', 
            'floor', 'block', 'area', 'address_line_2', 'addressline 2', 'address line two',
            'additional address', 'address details', 'address info', 'colony', 'sector',
            'phase', 'complex', 'apartments', 'tower', 'wing', 'extension'
        ],
        'landmark': [
            'landmark', 'near', 'nearby', 'beside', 'adjacent to', 'close to', 'in front of', 
            'opposite to', 'next to', 'behind', 'reference point', 'point of reference', 
            'famous place', 'notable location', 'vicinity', 'proximity', 'local landmark'
        ]
    }
    
    def __init__(self, 
                 region: str = 'india', 
                 variety_level: int = 2,
                 custom_profile: Optional[Dict] = None,
                 profiles_file: Optional[str] = None):
        """
        Initialize the form data manager
        
        Args:
            region: Region to use for form data values (india, usa, global)
            variety_level: How much variety to use in form filling (1=minimal, 3=extensive)
            custom_profile: Custom profile data to use
            profiles_file: Path to JSON file with multiple profiles
        """
        self.region = region.lower()
        self.variety_level = max(1, min(3, variety_level))  # Clamp between 1-3
        
        # Initialize form values based on region
        if self.region == 'india':
            self.form_values = self.INDIA_FORM_VALUES
        elif self.region == 'usa':
            self.form_values = self.USA_FORM_VALUES
        else:
            # Use global values (could be expanded for other regions)
            self.form_values = self.INDIA_FORM_VALUES
        
        # Load profiles from file if provided
        self.profiles = {}  # Change from list to dict for better key-based access
        if profiles_file and os.path.exists(profiles_file):
            try:
                with open(profiles_file, 'r') as f:
                    self.profiles = json.load(f)
                logger.info("Loaded %d profiles from %s", len(self.profiles), profiles_file)
            except Exception as e:
                logger.error("Error loading profiles from %s: %s", profiles_file, e)
        
        # Initialize custom values dictionary
        self.custom_values = {}
        
        # Add custom profile if provided
        if custom_profile:
            self.active_profile = custom_profile
        elif self.profiles:
            # Use a random profile from loaded profiles
            profile_id = random.choice(list(self.profiles.keys()))
            self.active_profile = self.profiles[profile_id]
            self.current_profile_id = profile_id
        else:
            # Generate a profile if none provided
            self.active_profile = self._generate_profile()
            self.current_profile_id = None
            
        logger.info("Form data manager initialized with region: %s, variety level: %s", region, variety_level)
        
    def _generate_profile(self) -> Dict[str, str]:
        """
        Generate a random profile with consistent information
        
        Returns:
            Dictionary with profile information
        """
        # Select random gender for consistent naming
        gender = random.choice(self.form_values['gender'])
        
        # Select first and last name based on gender
        if self.region == 'india':
            if gender == 'Male':
                first_name = random.choice([n for n in self.form_values['first_name'] 
                                        if n in ['Raj', 'Amit', 'Mohammed', 'Vikram', 'Sanjay']])
            else:
                first_name = random.choice([n for n in self.form_values['first_name'] 
                                        if n in ['Priya', 'Shreya', 'Ananya', 'Deepika', 'Kavita']])
        else:  # USA or other regions
            if gender == 'Male':
                first_name = random.choice([n for n in self.form_values['first_name']
                                        if n in ['John', 'Michael', 'David', 'Robert', 'Thomas']])
            else:
                first_name = random.choice([n for n in self.form_values['first_name']
                                        if n in ['Sarah', 'Jennifer', 'Lisa', 'Emily', 'Jessica']])
            
        last_name = random.choice(self.form_values['last_name'])
        full_name = f"{first_name} {last_name}"
        
        # Create email from name
        email_username = f"{first_name.lower()}.{last_name.lower()}"
        email_domain = random.choice(['gmail.com', 'yahoo.com', 'outlook.com', 'example.com'])
        email = f"{email_username}@{email_domain}"
        
        # Create username from name
        username_options = [
            f"{first_name.lower()}{last_name.lower()}",
            f"{first_name.lower()}_{last_name.lower()}",
            f"{first_name.lower()}{random.randint(1, 999)}",
            f"{first_name[0].lower()}{last_name.lower()}{random.randint(1, 99)}"
        ]
        username = random.choice(username_options)
        
        # Select city, state and pincode/zipcode that match
        region_idx = random.randint(0, 9)
        city = self.form_values['city'][region_idx]
        state = self.form_values['state'][region_idx]
        state_code = self.form_values['state_code'][region_idx]
        
        # Generate address
        address = random.choice(self.form_values['address'])
        address_line2 = random.choice(self.form_values['address_line2'])
        landmark = random.choice(self.form_values['landmark'])
        
        # Generate random birthdate (for adults)
        birth_year = random.choice(self.form_values['years'])
        birth_month = random.choice(self.form_values['months'])
        # Adjust days based on month
        max_days = 30
        if birth_month in [1, 3, 5, 7, 8, 10, 12]:
            max_days = 31
        elif birth_month == 2:
            max_days = 29 if (birth_year % 4 == 0 and birth_year % 100 != 0) or birth_year % 400 == 0 else 28
        birth_day = random.randint(1, max_days)
        
        # Format birthdate based on region
        if self.region == 'india':
            birthdate = f"{birth_day:02d}/{birth_month:02d}/{birth_year}"  # DD/MM/YYYY
            pincode = self.form_values['pincode'][region_idx]
            phone = f"+91 {random.randint(7, 9)}{random.randint(1000000, 9999999)}"
        else:  # USA or other regions
            birthdate = f"{birth_month:02d}/{birth_day:02d}/{birth_year}"  # MM/DD/YYYY
            zipcode = self.form_values['zipcode'][region_idx]
            phone = f"+1 ({random.randint(200, 999)}) {random.randint(100, 999)}-{random.randint(1000, 9999)}"
        
        age = datetime.now().year - birth_year
        
        # Create the base profile with common fields
        profile = {
            "gender": gender,
            "first_name": first_name,
            "last_name": last_name,
            "full_name": full_name,
            "email": email,
            "username": username,
            "password": random.choice(self.form_values['password']),
            "phone": phone,
            "address": address,
            "address_line2": address_line2,
            "landmark": landmark,
            "city": city,
            "state": state,
            "state_code": state_code,
            "birthdate": birthdate,
            "age": str(age),
            "education": random.choice(self.form_values['education']),
            "occupation": random.choice(self.form_values['occupation']),
            "marital_status": random.choice(self.form_values['marital_status']),
            "language": random.choice(self.form_values['language']),
            "default_text": random.choice(self.form_values['default_text'])
        }
        
        # Add region-specific fields
        if self.region == 'india':
            profile.update({
                "pincode": pincode,
                "country": "India",
                "aadhaar": random.choice(self.form_values['aadhaar']),
                "pan": random.choice(self.form_values['pan']),
                "gst": random.choice(self.form_values['gst']),
                "voter_id": random.choice(self.form_values['voter_id']),
                "passport": random.choice(self.form_values['passport']),
                "driving_license": random.choice(self.form_values['driving_license']),
                "electricity_consumer_no": random.choice(self.form_values['electricity_consumer_no']),
                "gas_consumer_no": random.choice(self.form_values['gas_consumer_no']),
                "vehicle_reg_no": random.choice(self.form_values['vehicle_reg_no'])
            })
        else:  # USA or other regions
            profile.update({
                "zipcode": zipcode,
                "country": "United States",
                "ssn": random.choice(self.form_values['ssn']),
                "passport": random.choice(self.form_values['passport']),
                "driving_license": random.choice(self.form_values['driving_license']),
                "state_id": random.choice(self.form_values['state_id']),
                "medicare": random.choice(self.form_values['medicare']),
                "ein": random.choice(self.form_values['ein']),
                "vehicle_reg_no": random.choice(self.form_values['vehicle_reg_no'])
            })
        
        return profile
        
    def determine_input_value(self, element: Dict[str, Any]) -> str:
        """
        Determine the appropriate value to enter in an input field based on its attributes
        
        Args:
            element: Dictionary with element data
            
        Returns:
            Value to enter in the input field
        """
        # Extract element attributes
        elem_id = element.get('id', '').lower().strip()
        elem_name = element.get('name', '').lower().strip()
        elem_type = element.get('type', '').lower().strip()
        elem_placeholder = element.get('placeholder', '').lower().strip()
        elem_class = ' '.join(element.get('class', [])).lower().strip() if isinstance(element.get('class'), list) else ''
        elem_label = element.get('ariaLabel', '').lower().strip()
        
        # Get label text if available
        label_text = element.get('labelText', '').lower()
        
        # Combine all textual attributes for context analysis
        context = f"{elem_id} {elem_name} {elem_placeholder} {elem_class} {elem_label} {label_text}".strip()
        
        # Check custom values first (highest priority)
        for field_name, pattern_list in self.custom_field_patterns.items():
            if self._match_terms(context, pattern_list):
                return self.custom_values.get(field_name, self.active_profile.get(field_name, ''))
        
        # Check for personal information fields
        
        # Name fields
        if self._match_terms(context, ['full name', 'fullname', 'name']):
            return self.active_profile['full_name']
            
        # Common search related fields
        if self._match_terms(context, ['search', 'query', 'find', 'lookup', 'find', 'look', ]):
            return random.choice(self.form_values['search_term'])
        
        if self._match_terms(context, ['first name', 'firstname', 'fname', 'given name']):
            return self.active_profile['first_name']
            
        if self._match_terms(context, ['last name', 'lastname', 'lname', 'surname', 'family name']):
            return self.active_profile['last_name']
        
        # Email field
        if elem_type == 'email' or self._match_terms(context, ['email', 'e-mail', 'mail']):
            return self.active_profile['email']
        
        # Phone fields
        if self._match_terms(context, ['phone', 'mobile', 'cell', 'tel', 'contact no', 'mobile no', 'contact number', 'mobile number', 'whatsapp']):
            return self.active_profile['phone']
            
        # Username fields
        if self._match_terms(context, ['username', 'user name', 'login id', 'loginid']):
            return self.active_profile['username']
            
        # Password fields
        if elem_type == 'password' or self._match_terms(context, ['password', 'pwd', 'pass']):
            return self.active_profile['password']
        
        # Birth date fields
        if self._match_terms(context, ['birth date', 'birthdate', 'date of birth', 'dob']):
            return self.active_profile['birthdate']
            
        # Age fields
        if self._match_terms(context, ['age', 'years old']):
            return self.active_profile['age']
            
        # Gender fields
        if self._match_terms(context, ['gender', 'sex']):
            return self.active_profile['gender']
            
        # Region-specific ID document fields
        if self.region == 'india':
            if self._match_terms(context, ['aadhaar', 'aadhar', 'uid', 'uidai']):
                return self.active_profile['aadhaar']
                
            if self._match_terms(context, ['pan', 'permanent account number', 'income tax']):
                return self.active_profile['pan']
                
            if self._match_terms(context, ['gst', 'gstin', 'goods and service tax', 'tax id']):
                return self.active_profile['gst']
                
            if self._match_terms(context, ['voter', 'voter id', 'election id', 'epic']):
                return self.active_profile['voter_id']
                
            if self._match_terms(context, ['electricity', 'electricity bill', 'consumer number', 'electricity connection']):
                return self.active_profile['electricity_consumer_no']
                
            if self._match_terms(context, ['gas', 'gas connection', 'gas consumer', 'lpg', 'cylinder']):
                return self.active_profile['gas_consumer_no']
        else:  # USA or other regions
            if self._match_terms(context, ['ssn', 'social security', 'social security number', 'tax id']):
                return self.active_profile['ssn']
                
            if self._match_terms(context, ['medicare', 'medicare number', 'health insurance']):
                return self.active_profile['medicare']
                
            if self._match_terms(context, ['ein', 'employer identification', 'tax id number', 'business tax']):
                return self.active_profile['ein']
                
            if self._match_terms(context, ['state id', 'identification card', 'state identification']):
                return self.active_profile['state_id']
        
        # Common ID fields across regions
        if self._match_terms(context, ['passport', 'passport number', 'passport no']):
            return self.active_profile['passport']
            
        if self._match_terms(context, ['driving license', 'driving licence', 'dl', 'driver license', 'driver\'s license']):
            return self.active_profile['driving_license']
            
        if self._match_terms(context, ['vehicle', 'registration', 'vehicle no', 'car number', 'rc', 'license plate']):
            return self.active_profile['vehicle_reg_no']
        
        # Address fields - using enhanced address patterns
        if self._match_terms(context, self.ADDRESS_PATTERNS['address_line1']):
            return self.active_profile['address']
            
        if self._match_terms(context, self.ADDRESS_PATTERNS['address_line2']):
            return self.active_profile['address_line2']
            
        if self._match_terms(context, self.ADDRESS_PATTERNS['landmark']):
            return self.active_profile['landmark']
            
        if self._match_terms(context, ['city', 'town', 'village', 'locality', 'municipal corporation', 'district']):
            return self.active_profile['city']
            
        if self._match_terms(context, ['state', 'province', 'region', 'territory']):
            return self.active_profile['state']
            
        # Postal code field - check for region-specific terms
        if self.region == 'india':
            if self._match_terms(context, ['pincode', 'postal code', 'zip', 'zip code', 'pin', 'postal']):
                return self.active_profile['pincode']
        else:  # USA or other regions
            if self._match_terms(context, ['zipcode', 'zip code', 'zip', 'postal code', 'postal']):
                return self.active_profile['zipcode']
            
        if self._match_terms(context, ['country', 'nation']):
            return self.active_profile['country']
            
        # Education and occupation
        if self._match_terms(context, ['education', 'qualification', 'degree', 'academic']):
            return self.active_profile['education']
            
        if self._match_terms(context, ['occupation', 'profession', 'job', 'employment', 'work']):
            return self.active_profile['occupation']
        
        # Other fields
        if self._match_terms(context, ['marital status', 'matrimonial status']):
            return self.active_profile['marital_status']
            
        if self._match_terms(context, ['language', 'mother tongue', 'preferred language']):
            return self.active_profile['language']
            
            
        # Check for exact field name match in custom values (fallback)
        if elem_name in self.custom_values:
            return self.custom_values[elem_name]
            
        # Default text for other fields
        return self.active_profile['default_text']
    
    @property
    def custom_field_patterns(self) -> Dict[str, List[str]]:
        """
        Get patterns for custom fields based on keys in custom_values
        
        Returns:
            Dictionary mapping custom field names to their potential patterns
        """
        patterns = {}
        for field_name in self.custom_values.keys():
            # Generate patterns based on field name
            field_patterns = [
                field_name,
                field_name.replace('_', ' '),
                field_name.replace('_', '-'),
                ' '.join([p.capitalize() for p in field_name.split('_')])
            ]
            patterns[field_name] = field_patterns
        return patterns
        
    def _match_terms(self, context: str, terms: List[str]) -> bool:
        """
        Check if any of the terms appear in the context
        
        Args:
            context: Text to search in
            terms: List of terms to search for
            
        Returns:
            True if any term is found in context
        """
        for term in terms:
            # Handle both exact match and word boundary matches
            if term in context or re.search(r'\b' + re.escape(term) + r'\b', context):
                return True
        return False
        
    def switch_profile(self, profile_id: Optional[str] = None) -> Dict[str, str]:
        """
        Switch to a different profile
        
        Args:
            profile_id: Specific profile ID to switch to, or None for random
            
        Returns:
            The new active profile
        """
        if profile_id and profile_id in self.profiles:
            # Switch to the specified profile
            self.active_profile = self.profiles[profile_id]
            self.current_profile_id = profile_id
        elif self.profiles:
            # Choose a different profile from available profiles
            available_profiles = {k: v for k, v in self.profiles.items() 
                                if v != self.active_profile}
            if available_profiles:
                self.current_profile_id = random.choice(list(available_profiles.keys()))
                self.active_profile = self.profiles[self.current_profile_id]
            else:
                self.active_profile = self._generate_profile()
                self.current_profile_id = None
        else:
            # Generate a new profile
            self.active_profile = self._generate_profile()
            self.current_profile_id = None
            
        # Reset custom values when switching profiles
        self.custom_values = {}
            
        logger.info("Switched to profile: %s", self.current_profile_id or 'generated')
        return self.active_profile
        
    def add_custom_value(self, field_name: str, value: str) -> None:
        """
        Add or update a custom value for field detection
        
        Args:
            field_name: Field name to add/update
            value: Value to set
        """
        self.custom_values[field_name] = value
        logger.info("Added custom value for field: %s", field_name)
        
    def remove_custom_value(self, field_name: str) -> bool:
        """
        Remove a custom value
        
        Args:
            field_name: Field name to remove
            
        Returns:
            True if removed, False if not found
        """
        if field_name in self.custom_values:
            del self.custom_values[field_name]
            logger.info("Removed custom value for field: %s", field_name)
            return True
        return False
        
    def get_current_profile(self) -> Dict[str, str]:
        """
        Get the current active profile
        
        Returns:
            Dictionary with the active profile data
        """
        return self.active_profile
        
    def get_custom_values(self) -> Dict[str, str]:
        """
        Get all custom values
        
        Returns:
            Dictionary with custom values
        """
        return self.custom_values
        
    def save_profiles(self, output_file: str) -> None:
        """
        Save current profiles to a file
        
        Args:
            output_file: Path to save the profiles
        """
        # Add current profile if it's not in the profiles dictionary
        if (self.current_profile_id is None) and self.active_profile:
            new_id = f"profile_{len(self.profiles) + 1}"
            self.profiles[new_id] = self.active_profile
            self.current_profile_id = new_id
            
        try:
            with open(output_file, 'w') as f:
                json.dump(self.profiles, f, indent=2)
            logger.info("Saved %d profiles to %s", len(self.profiles), output_file)
        except Exception as e:
            logger.error("Error saving profiles to %s: %s", output_file, e)
