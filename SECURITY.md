# Segurança e privacidade

O Recon processa arquivos localmente, mas os relatórios podem conter metadados corporativos. Trate entradas, saídas e chaves de pseudonimização como informações internas.

Para relatar uma vulnerabilidade, não publique dados de exemplo reais nem detalhes exploráveis em uma issue pública. Contate o mantenedor do repositório de forma privada, descrevendo impacto, versão afetada e uma reprodução mínima sem dados sensíveis.

O projeto neutraliza fórmulas em dicionários XLSX e usa HMAC com `RECON_PSEUDONYMIZATION_KEY` nos scripts gerados para pseudonimização. Isso não transforma dados pessoais em dados anonimizados.
