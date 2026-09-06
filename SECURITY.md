# Segurança e privacidade

O Recon processa arquivos localmente, mas os relatórios podem conter metadados corporativos. Trate entradas, saídas e chaves de pseudonimização como informações internas.

## Relatar uma vulnerabilidade

Não publique dados reais nem detalhes exploráveis em issue pública. Abra uma comunicação privada com o mantenedor do repositório e informe impacto, versão afetada, ambiente e uma reprodução mínima sem dados sensíveis. Se o repositório disponibilizar um canal de segurança, prefira-o ao contato público.

O relato deve permitir reproduzir o problema sem anexar planilhas, credenciais, tokens ou chaves. A confirmação de recebimento e o prazo de correção dependem da gravidade e da possibilidade de reprodução.

## Limites de proteção

O projeto neutraliza fórmulas em dicionários XLSX e usa HMAC com `RECON_PSEUDONYMIZATION_KEY` nos scripts gerados para pseudonimização. Isso não transforma dados pessoais em dados anonimizados.

Não inclua a chave de pseudonimização, strings de conexão, saídas de relatórios ou bases corporativas no Git, em tickets públicos ou em ferramentas externas.
