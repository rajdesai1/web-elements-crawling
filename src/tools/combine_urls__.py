#!/usr/bin/env python3
"""
Script to combine URLs from multiple sources, remove duplicates, and validate each URL.
"""

import json
import os
import argparse
import sys
from urllib.parse import urlparse
from pathlib import Path
import re
from collections import Counter

def is_valid_url(url):
    """
    Check if a string is a valid URL.
    
    Args:
        url (str): URL to validate
    
    Returns:
        bool: True if valid URL, False otherwise
    """
    if not isinstance(url, str):
        return False
        
    # Ensure it has a scheme and netloc
    try:
        if not url.startswith("http://") and not url.startswith("https://"):
            url = f"https://{url}"
            
        result = urlparse(url)
        if not all([result.scheme, result.netloc]):
            return False
            
        # Additional validation for domain format
        domain_pattern = r'^([a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$'
        return bool(re.match(domain_pattern, result.netloc))
    except:
        return False

def normalize_url(url):
    """
    Normalize URL format (add https:// if missing, strip trailing slashes).
    
    Args:
        url (str): URL to normalize
    
    Returns:
        str: Normalized URL
    """
    url = url.strip()
    
    # Convert domain-only URLs to full URLs
    if not url.startswith("http://") and not url.startswith("https://"):
        url = f"https://{url}"
        
    # Remove trailing slashes
    while url.endswith("/"):
        url = url[:-1]
        
    return url

def extract_domain(url):
    """
    Extract domain from URL.
    
    Args:
        url (str): URL to extract domain from
    
    Returns:
        str: Domain name
    """
    try:
        if not url.startswith("http://") and not url.startswith("https://"):
            url = f"https://{url}"
            
        parsed = urlparse(url)
        domain = parsed.netloc
        
        # Remove www. if present
        if domain.startswith("www."):
            domain = domain[4:]
            
        return domain
    except:
        return url

def load_json_urls(json_file):
    """
    Load URLs from a JSON file.
    
    Args:
        json_file (str): Path to JSON file
    
    Returns:
        list: List of URLs
    """
    try:
        with open(json_file, 'r') as f:
            data = json.load(f)
            
        # Handle different JSON structures
        if isinstance(data, list):
            # If it's a list, extract strings or domain/url fields
            urls = []
            for item in data:
                if isinstance(item, str):
                    urls.append(item)
                elif isinstance(item, dict):
                    # Check for common URL fields
                    for field in ['url', 'domain', 'website', 'site', 'link']:
                        if field in item and isinstance(item[field], str):
                            urls.append(item[field])
                            break
            return urls
                    
        elif isinstance(data, dict):
            # If it's a dictionary, look for keys that might contain URLs
            for key in ['urls', 'domains', 'websites', 'sites', 'links']:
                if key in data and isinstance(data[key], list):
                    return data[key]
                    
            # If no obvious list of URLs, extract all string values
            urls = []
            def extract_strings(obj, urls_list):
                if isinstance(obj, dict):
                    for k, v in obj.items():
                        if isinstance(v, str) and is_valid_url(v):
                            urls_list.append(v)
                        elif isinstance(v, (dict, list)):
                            extract_strings(v, urls_list)
                elif isinstance(obj, list):
                    for item in obj:
                        if isinstance(item, str) and is_valid_url(item):
                            urls_list.append(item)
                        elif isinstance(item, (dict, list)):
                            extract_strings(item, urls_list)
                            
            extract_strings(data, urls)
            return urls
    except Exception as e:
        print(f"Error loading JSON file {json_file}: {e}")
        return []

def load_text_urls(text_file):
    """
    Load URLs from a text file (one per line).
    
    Args:
        text_file (str): Path to text file
    
    Returns:
        list: List of URLs
    """
    try:
        with open(text_file, 'r') as f:
            return [line.strip() for line in f if line.strip()]
    except Exception as e:
        print(f"Error loading text file {text_file}: {e}")
        return []

def combine_and_validate_urls(sources, output_file=None, invalid_file=None, duplicate_file=None):
    """
    Combine URLs from multiple sources, validate, and remove duplicates.
    
    Args:
        sources (list): List of source files
        output_file (str): Path to output file for valid unique URLs
        invalid_file (str): Path to file for invalid URLs
        duplicate_file (str): Path to file for exact duplicate URLs
    
    Returns:
        tuple: (valid_urls, invalid_urls, duplicate_urls)
    """
    all_urls = []
    
    # Load URLs from all sources
    for source in sources:
        if not os.path.exists(source):
            print(f"Warning: Source file {source} does not exist")
            continue
            
        if source.lower().endswith('.json'):
            all_urls.extend(load_json_urls(source))
        else:
            all_urls.extend(load_text_urls(source))
    
    # Normalize URLs and count occurrences
    normalized_urls = [normalize_url(url) for url in all_urls if url]
    url_counter = Counter(normalized_urls)
    
    # Process URLs
    valid_urls = []
    invalid_urls = []
    duplicate_urls = []
    seen_urls = set()
    
    for url, count in url_counter.items():
        # Check if URL is valid
        if not is_valid_url(url):
            invalid_urls.append(url)
            continue
            
        # This is a valid URL
        if count > 1:
            # This URL appears multiple times (exact duplicate)
            duplicate_info = {
                'url': url,
                'count': count
            }
            duplicate_urls.append(duplicate_info)
        
        # Add to valid URLs (only once)
        valid_urls.append(url)
    
    # Sort URLs for consistency
    valid_urls = sorted(valid_urls)
    invalid_urls = sorted(invalid_urls)
    duplicate_urls = sorted(duplicate_urls, key=lambda x: x['url'])
    
    # Write to output file if specified
    if output_file:
        with open(output_file, 'w') as f:
            f.write('\n'.join(valid_urls))
        
        print(f"Wrote {len(valid_urls)} valid URLs to {output_file}")
    
    # Write invalid URLs to file if specified
    if invalid_file and invalid_urls:
        with open(invalid_file, 'w') as f:
            f.write('\n'.join(invalid_urls))
        
        print(f"Wrote {len(invalid_urls)} invalid URLs to {invalid_file}")
    
    # Write duplicate URLs to file if specified
    if duplicate_file and duplicate_urls:
        with open(duplicate_file, 'w') as f:
            for dup in duplicate_urls:
                f.write(f"{dup['url']} (found {dup['count']} times)\n")
        
        print(f"Wrote {len(duplicate_urls)} duplicated URLs to {duplicate_file} (URLs that appear more than once)")
    
    # Count unique domains for information
    unique_domains = set(extract_domain(url) for url in valid_urls)
    
    return valid_urls, invalid_urls, duplicate_urls, len(unique_domains)

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Combine URLs from multiple sources, remove duplicates, and validate")
    parser.add_argument('--sources', nargs='+', help="Source files containing URLs")
    parser.add_argument('--output', default='validated_urls.txt', help="Output file for valid URLs")
    parser.add_argument('--invalid', default='invalid_urls.txt', help="Output file for invalid URLs")
    parser.add_argument('--duplicates', default='duplicate_urls.txt', help="Output file for duplicate URLs")
    parser.add_argument('--default-sources', action='store_true', help="Use default sources: ranked_domains.json, unique_urls.txt, combined_urls.txt")
    
    args = parser.parse_args()
    
    if args.default_sources:
        sources = []
        for file in ['ranked_domains.json', 'unique_urls.txt', 'combined_urls.txt']:
            if os.path.exists(file):
                sources.append(file)
        
        if not sources:
            print("No default source files found!")
            sys.exit(1)
    elif not args.sources:
        parser.print_help()
        sys.exit(1)
    else:
        sources = args.sources
    
    valid_urls, invalid_urls, duplicate_urls, unique_domain_count = combine_and_validate_urls(
        sources, args.output, args.invalid, args.duplicates
    )
    
    print(f"\nSummary:")
    print(f"  Total valid unique URLs: {len(valid_urls)}")
    print(f"  Total invalid URLs: {len(invalid_urls)}")
    print(f"  Total URLs that appear multiple times: {len(duplicate_urls)}")
    print(f"  Total unique domains: {unique_domain_count}")
    print(f"  Total URLs processed: {len(all_urls) if 'all_urls' in locals() else 'N/A'}")

if __name__ == "__main__":
    main() 