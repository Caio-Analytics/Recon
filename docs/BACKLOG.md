# Backlog do Recon

## Relações entre tabelas sem chave explícita

**Problema.** Algumas bases não têm uma chave direta identificável, embora a
relação possa ser importante para a análise.

**Proposta.** Investigar uma etapa opcional de hipóteses de relacionamento que
combine nomes semanticamente parecidos, sobreposição de valores, formatos e
cardinalidade. O resultado deve ser uma sugestão para revisão da pessoa
analista, não uma relação assumida pelo sistema.

**Guardas necessárias.** Não criar `join` automático nem afirmar que duas
colunas se relacionam sem evidência explicável. Definir limiares, mostrar a
confiança e oferecer validações que reduzam falsos positivos.

**Critério de aceite.** Cada hipótese informa as evidências usadas, a
confiança, exemplos não sensíveis e uma forma de rejeitá-la. Bases sem
evidência suficiente não recebem sugestão.

**Prioridade.** Média. A capacidade deve continuar opcional até ser avaliada
contra conjuntos de dados com relações conhecidas.
