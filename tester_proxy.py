import re

def extract_proxies_from_text(text):
    """
    Extracts Telegram proxy URLs from a given text using regex.
    """
    pattern = r'https://t\.me/proxy\?server=[^&\s]*&port=\d+&secret=[^&\s]*&@Data_proxy'
    proxies = re.findall(pattern, text)
    return proxies

def save_proxies_to_file(proxy_list, filename='proxies.txt'):
    """
    Saves the list of proxies to the beginning of the specified file.
    Keeps the existing content if the file exists.
    """
    existing_content = ""
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            existing_content = f.read()
    except FileNotFoundError:
        existing_content = ""

    new_content = '\n'.join(proxy_list)
    if existing_content:
        new_content += '\n' + existing_content

    with open(filename, 'w', encoding='utf-8') as f:
        f.write(new_content)

    print(f"\nFound {len(proxy_list)} proxies and saved them to '{filename}'.")

def read_proxies_from_file(filename='test.txt'):
    """
    Reads the content of the specified file.
    """
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            content = f.read()
        return content
    except FileNotFoundError:
        print(f"File '{filename}' not found.")
        return ""

# Main execution
if __name__ == "__main__":
    input_text = read_proxies_from_file('test.txt')
    if input_text:
        found_proxies = extract_proxies_from_text(input_text)
        if found_proxies:
            save_proxies_to_file(found_proxies)
        else:
            print("\nNo valid proxies found.")
    else:
        print("\nNo content was read from 'test.txt'.")