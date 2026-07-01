"""
MyGene.info tool - get gene information and annotations
"""

import requests
import os
from typing import Dict, Any, List, Optional


def get_gene_summary(symbol: str) -> Dict[str, Any]:
    """
    Get gene information from MyGene.info
    
    Args:
        symbol: Gene symbol (e.g., 'BRCA1', 'TP53')
        
    Returns:
        Dictionary containing gene information
    """
    try:
        base_url = "https://mygene.info/v3"
        
        # First, query to get gene ID
        query_url = f"{base_url}/query"
        query_params = {
            "q": symbol,
            "species": "human",
            "fields": "symbol,name,entrezgene,ensembl.gene,summary,type_of_gene",
            "size": 1
        }
        
        response = requests.get(query_url, params=query_params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if not data.get("hits"):
            return {
                "symbol": symbol,
                "error": f"No gene found with symbol '{symbol}'",
                "found": False
            }
        
        gene_data = data["hits"][0]
        
        # Get detailed information if we have a gene ID
        gene_id = gene_data.get("_id")
        if gene_id:
            detail_url = f"{base_url}/gene/{gene_id}"
            detail_params = {
                "fields": "symbol,name,entrezgene,ensembl.gene,summary,type_of_gene,genomic_pos,pathway,go,interpro,homologene,pharmgkb"
            }
            
            detail_response = requests.get(detail_url, params=detail_params, timeout=10)
            detail_response.raise_for_status()
            detailed_data = detail_response.json()
            
            return _format_gene_data(detailed_data)
        else:
            return _format_gene_data(gene_data)
            
    except requests.exceptions.RequestException as e:
        return {"symbol": symbol, "error": f"Network error: {str(e)}", "found": False}
    except Exception as e:
        return {"symbol": symbol, "error": f"Error fetching gene data: {str(e)}", "found": False}


def _format_gene_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """Format gene data into a standardized structure"""
    return {
        "symbol": data.get("symbol", "Unknown"),
        "name": data.get("name", "Unknown"),
        "entrez_id": data.get("entrezgene"),
        "ensembl_id": data.get("ensembl", {}).get("gene") if data.get("ensembl") else None,
        "type": data.get("type_of_gene", "Unknown"),
        "summary": data.get("summary", "No summary available"),
        "genomic_position": _format_genomic_position(data.get("genomic_pos")),
        "pathways": _extract_pathways(data.get("pathway", [])),
        "go_terms": _extract_go_terms(data.get("go", {})),
        "interpro_domains": _extract_interpro(data.get("interpro", [])),
        "homologs": _extract_homologs(data.get("homologene", {})),
        "pharmgkb": data.get("pharmgkb", {}),
        "found": True,
        "source": "MyGene.info"
    }


def _format_genomic_position(genomic_pos: Any) -> Dict[str, Any]:
    """Format genomic position information"""
    if not genomic_pos:
        return {}
    
    if isinstance(genomic_pos, dict):
        return {
            "chr": genomic_pos.get("chr"),
            "start": genomic_pos.get("start"),
            "end": genomic_pos.get("end"),
            "strand": genomic_pos.get("strand")
        }
    
    return {"raw": str(genomic_pos)}


def _extract_pathways(pathways: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Extract pathway information"""
    if not pathways:
        return []
    
    pathway_list = []
    for pathway in pathways:
        if isinstance(pathway, dict):
            pathway_list.append({
                "name": pathway.get("name", "Unknown pathway"),
                "id": pathway.get("id", "Unknown ID"),
                "source": pathway.get("source", "Unknown source")
            })
    
    return pathway_list


def _extract_go_terms(go_data: Dict[str, Any]) -> Dict[str, List[str]]:
    """Extract GO terms by category"""
    if not go_data:
        return {}
    
    go_terms = {"biological_process": [], "molecular_function": [], "cellular_component": []}
    
    for category, terms in go_data.items():
        if category in go_terms and isinstance(terms, list):
            go_terms[category] = [
                term.get("term", "Unknown term") for term in terms
                if isinstance(term, dict) and term.get("term")
            ]
    
    return go_terms


def _extract_interpro(interpro_data: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Extract InterPro domain information"""
    if not interpro_data:
        return []
    
    domains = []
    for domain in interpro_data:
        if isinstance(domain, dict):
            domains.append({
                "name": domain.get("name", "Unknown domain"),
                "id": domain.get("id", "Unknown ID"),
                "type": domain.get("type", "Unknown type")
            })
    
    return domains


def _extract_homologs(homolog_data: Dict[str, Any]) -> Dict[str, Any]:
    """Extract homolog information"""
    if not homolog_data:
        return {}
    
    return {
        "homologene_id": homolog_data.get("homologene"),
        "genes": homolog_data.get("genes", [])
    }


def get_gene_by_entrez(entrez_id: str) -> Dict[str, Any]:
    """
    Get gene information by Entrez ID
    
    Args:
        entrez_id: Entrez gene ID
        
    Returns:
        Dictionary containing gene information
    """
    try:
        base_url = "https://mygene.info/v3"
        url = f"{base_url}/gene/{entrez_id}"
        
        params = {
            "fields": "symbol,name,entrezgene,ensembl.gene,summary,type_of_gene,genomic_pos,pathway,go,interpro,homologene,pharmgkb"
        }
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        return _format_gene_data(data)
        
    except requests.exceptions.RequestException as e:
        return {"entrez_id": entrez_id, "error": f"Network error: {str(e)}", "found": False}
    except Exception as e:
        return {"entrez_id": entrez_id, "error": f"Error fetching gene data: {str(e)}", "found": False}


def search_genes_by_name(name: str, limit: int = 5) -> List[Dict[str, Any]]:
    """
    Search for genes by name
    
    Args:
        name: Gene name to search for
        limit: Maximum number of results
        
    Returns:
        List of matching genes
    """
    try:
        base_url = "https://mygene.info/v3"
        query_url = f"{base_url}/query"
        
        params = {
            "q": name,
            "species": "human",
            "fields": "symbol,name,entrezgene,ensembl.gene,summary",
            "size": limit
        }
        
        response = requests.get(query_url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        results = []
        for hit in data.get("hits", []):
            results.append({
                "symbol": hit.get("symbol", "Unknown"),
                "name": hit.get("name", "Unknown"),
                "entrez_id": hit.get("entrezgene"),
                "ensembl_id": hit.get("ensembl", {}).get("gene") if hit.get("ensembl") else None,
                "summary": hit.get("summary", "No summary available")
            })
        
        return results
        
    except requests.exceptions.RequestException as e:
        return [{"error": f"Network error: {str(e)}"}]
    except Exception as e:
        return [{"error": f"Error searching genes: {str(e)}"}]
