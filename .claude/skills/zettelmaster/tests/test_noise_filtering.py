#!/usr/bin/env python3
"""
Test script to demonstrate improved noise filtering in Zettelmaster
"""
from zettelmaster.noise_filter import NoiseFilter


def test_corporate_content():
    """Test filtering of corporate/marketing content"""
    
    corporate_text = """
    Our innovative platform leverages cutting-edge technology to transform 
    the way organizations approach their digital transformation journey. 
    This comprehensive solution empowers teams to unlock their full potential
    and drive unprecedented value across the enterprise.
    
    The system seamlessly integrates with existing infrastructure to enable
    organizations to:
    - Leverage best-in-class analytics capabilities
    - Drive innovation through robust frameworks
    - Transform business processes holistically
    - Empower stakeholders with actionable insights
    
    It should be noted that this paradigm shift represents a game-changing
    approach to solving various challenges. Generally speaking, users tend
    to find the platform somewhat useful for their needs.
    
    Technical specifications:
    - API response time: 200ms average
    - Supports REST, GraphQL, and WebSocket protocols
    - Database: PostgreSQL 14 with read replicas
    - Authentication: OAuth 2.0 and JWT tokens
    - Deployment: Kubernetes on AWS EKS
    - Data retention: 90 days for logs, 7 years for audit
    
    The architecture consists of microservices communicating via message queue.
    Rate limiting prevents more than 1000 requests per minute per client.
    Data encryption uses AES-256 for storage and TLS 1.3 for transport.
    """
    
    filter = NoiseFilter()
    result = filter.filter_content(corporate_text)
    
    print("=" * 60)
    print("CORPORATE CONTENT FILTERING TEST")
    print("=" * 60)
    print(f"Original: {result.original_length} chars")
    print(f"Filtered: {result.filtered_length} chars") 
    print(f"Removed: {result.removed_percentage:.1f}%")
    print()
    
    print("EXTRACTED FACTS:")
    for fact in result.facts:
        print(f"  • {fact}")
    print()
    
    print("EXTRACTED DEFINITIONS:")
    for term, defn in result.definitions.items():
        print(f"  • {term}: {defn}")
    print()
    
    print("CONCISE SUMMARY:")
    print(filter.generate_concise_summary(result))
    print()


def test_technical_content():
    """Test filtering of technical documentation"""
    
    technical_text = """
    The authentication module implements a multi-factor authentication system
    that is considered to be highly secure and robust. It should be noted that
    various types of authentication methods are supported to some extent.
    
    Implementation details:
    - Password hashing: bcrypt with cost factor 12
    - Session timeout: 30 minutes idle, 8 hours absolute
    - MFA options: TOTP, SMS, hardware keys (FIDO2)
    - Rate limiting: 5 failed attempts triggers 15-minute lockout
    
    The system generally tends to perform well under load, handling up to
    10,000 concurrent sessions. Obviously, this represents a significant 
    improvement over the previous solution which could only handle various
    numbers of users depending on different factors.
    
    Database schema includes users table with email (unique), password_hash,
    mfa_secret, and last_login timestamp. Sessions table tracks session_id,
    user_id, created_at, and expires_at. Failed login attempts are logged
    in security_events table.
    
    Error codes:
    - 401: Invalid credentials
    - 403: Account locked
    - 429: Rate limit exceeded
    """
    
    filter = NoiseFilter()
    result = filter.filter_content(technical_text)
    
    print("=" * 60)
    print("TECHNICAL CONTENT FILTERING TEST")
    print("=" * 60)
    print(f"Original: {result.original_length} chars")
    print(f"Filtered: {result.filtered_length} chars")
    print(f"Removed: {result.removed_percentage:.1f}%")
    print()
    
    print("EXTRACTED FACTS:")
    for fact in result.facts:
        print(f"  • {fact}")
    print()
    
    print("CONCISE SUMMARY:")
    print(filter.generate_concise_summary(result))
    

def test_vague_content():
    """Test filtering of vague, meaningless content"""
    
    vague_text = """
    There are various approaches to handling this particular situation.
    Some organizations might choose to implement certain types of solutions
    while others may opt for different kinds of strategies. It really 
    depends on a number of factors that should be considered.
    
    Generally speaking, it's important to note that many aspects need to
    be taken into account. Obviously, different teams will have somewhat
    different perspectives on what might work best. To some extent, the
    choice of approach is relatively flexible.
    
    It goes without saying that careful consideration should be given to
    all the various options available. Needless to say, there are many
    ways to potentially address these challenges, more or less.
    """
    
    filter = NoiseFilter()
    result = filter.filter_content(vague_text)
    
    print("=" * 60)
    print("VAGUE CONTENT FILTERING TEST")
    print("=" * 60)
    print(f"Original: {result.original_length} chars")
    print(f"Filtered: {result.filtered_length} chars")
    print(f"Removed: {result.removed_percentage:.1f}%")
    print()
    
    if not result.facts and not result.concepts and not result.definitions:
        print("✓ CORRECTLY IDENTIFIED AS CONTENTLESS")
        print("  No meaningful facts, concepts, or definitions extracted")
    else:
        print("⚠ Warning: Extracted content from vague text:")
        for fact in result.facts:
            print(f"  • {fact}")
    

if __name__ == "__main__":
    test_corporate_content()
    print("\n")
    test_technical_content()
    print("\n")
    test_vague_content()