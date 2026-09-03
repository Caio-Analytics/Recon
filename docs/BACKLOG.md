# Backlog do Recon

## Relações entre tabelas sem chave explícita

Investigar uma etapa opcional de **hipóteses de relacionamento** para bases que
não tenham uma chave direta identificável. Ela pode combinar evidências como
nomes semanticamente parecidos, sobreposição de valores, formatos e
cardinalidade para sugerir uma relação a ser revisada pela pessoa analista.

Não deve criar `join` automático nem afirmar que duas colunas se relacionam
sem evidência explicável. Antes de implementar, definir limiares, apresentar a
confiança e oferecer validações para reduzir falsos positivos.
