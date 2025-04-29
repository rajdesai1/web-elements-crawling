import os
import glob

# Directory containing the URL files
directory = '/Users/rajdesai/Codebase/TRANCE/elements_crawling/sitemap_results/sample'

# Output file path
output_file = os.path.join("/Users/rajdesai/Codebase/TRANCE/elements_crawling/sitemap_results", 'combined_urls.txt')

# Get all text files in the directory
url_files = glob.glob(os.path.join(directory, '*_urls.txt'))

# Combine all files
with open(output_file, 'w', encoding='utf-8') as outfile:
    for url_file in url_files:
        # Only process files that have content
        if os.path.getsize(url_file) > 0:
            try:
                with open(url_file, 'r', encoding='utf-8') as infile:
                    content = infile.read()
                    outfile.write(content)
                    if not content.endswith('\n'):
                        outfile.write('\n')
                    # outfile.write('\n')  # Add blank line between files
            except UnicodeDecodeError:
                # Try again with a different encoding
                try:
                    with open(url_file, 'r', encoding='latin-1') as infile:
                        content = infile.read()
                        outfile.write(content)
                        if not content.endswith('\n'):
                            outfile.write('\n')
                        # outfile.write('\n')  # Add blank line between files
                except Exception as e:
                    outfile.write(f"[Error reading file: {str(e)}]\n\n")

print(f"Combined URLs from {len(url_files)} files into {output_file}") 