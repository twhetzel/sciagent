"""
PubMed tool - fetch scientific articles from PubMed
"""

import requests
import os
from typing import Dict, Any, List
from bs4 import BeautifulSoup


def fetch_pubmed(query: str, max_results: int = 10) -> Dict[str, Any]:
    """
    Fetch articles from PubMed based on a search query
    
    Args:
        query: Search query string
        max_results: Maximum number of results to return
        
    Returns:
        Dictionary containing search results
    """
    try:
        # PubMed E-utilities API endpoint
        base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
        
        # Step 1: Search for PMIDs
        search_url = f"{base_url}esearch.fcgi"
        search_params = {
            "db": "pubmed",
            "term": query,
            "retmax": max_results,
            "retmode": "json",
            "tool": os.getenv("PUBMED_TOOL", "sciagent"),
            "email": os.getenv("PUBMED_EMAIL", "")
        }
        
        search_response = requests.get(search_url, params=search_params, timeout=10)
        search_response.raise_for_status()
        search_data = search_response.json()
        
        if "esearchresult" not in search_data:
            return {"error": "Invalid response from PubMed API", "results": []}
        
        pmids = search_data["esearchresult"].get("idlist", [])
        
        if not pmids:
            return {
                "query": query,
                "total_found": 0,
                "results": [],
                "message": "No articles found for the given query"
            }
        
        # Step 2: Fetch article details
        fetch_url = f"{base_url}efetch.fcgi"
        fetch_params = {
            "db": "pubmed",
            "id": ",".join(pmids),
            "retmode": "xml",
            "tool": os.getenv("PUBMED_TOOL", "sciagent"),
            "email": os.getenv("PUBMED_EMAIL", "")
        }
        
        fetch_response = requests.get(fetch_url, params=fetch_params, timeout=15)
        fetch_response.raise_for_status()
        
        # Parse XML response
        soup = BeautifulSoup(fetch_response.text, 'xml')
        articles = []
        
        for article in soup.find_all('PubmedArticle'):
            article_data = _parse_pubmed_article(article)
            if article_data:
                articles.append(article_data)
        
        return {
            "query": query,
            "total_found": len(articles),
            "results": articles,
            "source": "PubMed"
        }
        
    except requests.exceptions.RequestException as e:
        return {"error": f"Network error: {str(e)}", "results": []}
    except Exception as e:
        return {"error": f"Error fetching PubMed data: {str(e)}", "results": []}


def _parse_pubmed_article(article_xml) -> Dict[str, Any]:
    """Parse a single PubMed article from XML"""
    try:
        # Extract basic information
        pmid = article_xml.find('MedlineCitation').find('PMID').text
        
        # Article title
        title_elem = article_xml.find('MedlineCitation').find('Article').find('ArticleTitle')
        title = title_elem.text if title_elem else "No title"
        
        # Authors
        authors = []
        author_list = article_xml.find('MedlineCitation').find('Article').find('AuthorList')
        if author_list:
            for author in author_list.find_all('Author'):
                last_name = author.find('LastName')
                first_name = author.find('ForeName')
                if last_name:
                    author_name = last_name.text
                    if first_name:
                        author_name += f", {first_name.text}"
                    authors.append(author_name)
        
        # Journal information
        journal = article_xml.find('MedlineCitation').find('Article').find('Journal')
        journal_title = journal.find('Title').text if journal.find('Title') else "Unknown journal"
        
        # Publication date
        pub_date = journal.find('JournalIssue').find('PubDate')
        year = pub_date.find('Year').text if pub_date and pub_date.find('Year') else "Unknown year"
        
        # Abstract
        abstract = ""
        abstract_elem = article_xml.find('MedlineCitation').find('Article').find('Abstract')
        if abstract_elem:
            abstract_text = abstract_elem.find('AbstractText')
            if abstract_text:
                abstract = abstract_text.text
        
        # DOI
        doi = ""
        article_ids = article_xml.find('PubmedData').find('ArticleIdList')
        if article_ids:
            for article_id in article_ids.find_all('ArticleId'):
                if article_id.get('IdType') == 'doi':
                    doi = article_id.text
                    break
        
        return {
            "pmid": pmid,
            "title": title,
            "authors": authors,
            "journal": journal_title,
            "year": year,
            "abstract": abstract,
            "doi": doi,
            "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
        }
        
    except Exception as e:
        print(f"Error parsing article: {str(e)}")
        return None


def search_pubmed_advanced(query: str, date_range: tuple = None, journal: str = None) -> Dict[str, Any]:
    """
    Advanced PubMed search with additional filters
    
    Args:
        query: Search query
        date_range: Tuple of (start_year, end_year)
        journal: Journal name to filter by
        
    Returns:
        Dictionary containing search results
    """
    # Build advanced query
    advanced_query = query
    
    if date_range:
        start_year, end_year = date_range
        advanced_query += f" AND {start_year}[PDAT]:{end_year}[PDAT]"
    
    if journal:
        advanced_query += f" AND {journal}[Journal]"
    
    return fetch_pubmed(advanced_query)
