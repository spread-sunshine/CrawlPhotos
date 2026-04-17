import requests
try:
    r = requests.get('http://localhost:8000/api/v1/photos?page=1&page_size=2')
    with open('d:/ugit/Test/CrawlPhotos/test_api/test_api.txt', 'w') as f:
        f.write(f'Status: {r.status_code}\n')
        f.write(f'Body: {r.text[:1000]}\n')
except Exception as e:
    with open('d:/ugit/Test/CrawlPhotos/test_api/test_api.txt', 'w') as f:
        f.write(f'Error: {e}\n')
