import requests

def find_articles(author, year, title, api_key, count=25, start=0):
    url = "https://api.elsevier.com/content/search/sciencedirect"

    headers = {
        'Accept': 'application/json',
        'X-ELS-APIKey': api_key
    }

    query = f'AUTHOR({author}) AND TITLE({title}) AND PUBYEAR IS {year}'

    params = {
        'query': query,
        'count': count,
        'start': start
    }

    response = requests.get(url, headers=headers, params=params)

    if response.status_code == 200:
        return response.json()
    else:
        response.raise_for_status()

# Example usage:
api_key = "fea84b364ab661e3cf955f0f48f43fb9"
author = "Perrault"
year = "2012"
title = "THE PACE OF CULTURAL EVOLUTION"

articles_data = find_articles(author, year, title, api_key)

print(articles_data)


def get_article_citations(scopus_id, api_key, exclude_self=False, count=25, start=0):
    url = "https://api.elsevier.com/content/abstract/citations"

    headers = {
        'Accept': 'application/json',
        'X-ELS-APIKey': api_key
    }

    params = {
        'scopus_id': scopus_id,
        'start': start,
        'count': count
    }

    if exclude_self:
        params['citation'] = 'exclude-self'

    response = requests.get(url, headers=headers, params=params)

    if response.status_code == 200:
        return response.json()
    else:
        response.raise_for_status()

# Example usage:
scopus_id = "85000000001" 

citations_data = get_article_citations(scopus_id, api_key)

print(citations_data)