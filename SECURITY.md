# Segurança e privacidade

O Recon processa arquivos localmente, mas os relatórios podem conter metadados corporativos. Trate entradas, saídas e chaves de pseudonimização como informações internas.

## Relatar uma vulnerabilidade

Não publique dados reais nem detalhes exploráveis em issue pública. Use o relato privado do GitHub: na aba **Security** do repositório, clique em **Report a vulnerability** ([link direto](https://github.com/Caio-Analytics/recon-data-profiler/security/advisories/new)). Se a opção não estiver disponível, entre em contato com o mantenedor pelo perfil [@Caio-Analytics](https://github.com/Caio-Analytics) pedindo um canal privado, sem descrever a falha na mensagem inicial.

Informe impacto, versão afetada, ambiente e uma reprodução mínima sem dados sensíveis.

O relato deve permitir reproduzir o problema sem anexar planilhas, credenciais, tokens ou chaves. A confirmação de recebimento e o prazo de correção dependem da gravidade e da possibilidade de reprodução.

## Limites de proteção

O projeto neutraliza fórmulas em dicionários XLSX e usa HMAC com `RECON_PSEUDONYMIZATION_KEY` nos scripts gerados para pseudonimização. Isso não transforma dados pessoais em dados anonimizados.

Não inclua a chave de pseudonimização, strings de conexão, saídas de relatórios ou bases corporativas no Git, em tickets públicos ou em ferramentas externas.
