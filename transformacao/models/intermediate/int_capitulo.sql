-- Capítulos da CID-10, pelo intervalo do código de três caracteres.
-- Os intervalos não se sobrepõem: uma CID cai em no máximo um capítulo.
select * from (
    values
    ('01', 'A00', 'B99', 'Doenças infecciosas e parasitárias'),
    ('02', 'C00', 'D48', 'Neoplasias'),
    ('03', 'D50', 'D89', 'Doenças do sangue'),
    ('04', 'E00', 'E90', 'Doenças endócrinas'),
    ('05', 'F00', 'F99', 'Transtornos mentais'),
    ('06', 'G00', 'G99', 'Doenças do sistema nervoso'),
    ('07', 'H00', 'H59', 'Doenças do olho'),
    ('08', 'H60', 'H95', 'Doenças do ouvido'),
    ('09', 'I00', 'I99', 'Doenças do aparelho circulatório'),
    ('10', 'J00', 'J99', 'Doenças do aparelho respiratório'),
    ('11', 'K00', 'K93', 'Doenças do aparelho digestivo'),
    ('12', 'L00', 'L99', 'Doenças da pele'),
    ('13', 'M00', 'M99', 'Doenças do sistema osteomuscular'),
    ('14', 'N00', 'N99', 'Doenças do aparelho geniturinário'),
    ('15', 'O00', 'O99', 'Gravidez, parto e puerpério'),
    ('16', 'P00', 'P96', 'Afecções do período perinatal'),
    ('17', 'Q00', 'Q99', 'Malformações congênitas'),
    ('18', 'R00', 'R99', 'Sintomas e sinais'),
    ('19', 'S00', 'T98', 'Lesões e envenenamentos'),
    ('20', 'V01', 'Y98', 'Causas externas'),
    ('21', 'Z00', 'Z99', 'Fatores que influenciam o estado de saúde'),
    ('22', 'U00', 'U99', 'Códigos para propósitos especiais')
) as capitulo(capitulo_cid, inicio, fim, capitulo_nome)
