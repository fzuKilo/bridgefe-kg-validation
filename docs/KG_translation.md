NOTE: All texts in this document are reproduced verbatim from the implementation used in the experiments. The rule and clause nodes of the knowledge graph (KG) were transcribed from the Chinese design codes and store their titles, texts, and notes in Chinese; they were passed to the backbone LLMs in this form (Section S1.5 for C2, and through the KG query tools for C3–C5). The term 单梁（脊梁） in rule MR-01 denotes the spine-beam idealization of the manuscript (value "spine_beam_2d"). English translations of these texts are given in Section S1.12; they were not used in the experiments.

## S1.12 English translation of the KG rules and clauses quoted in Section S1.5

MR-01, structural idealization: For the global analysis of straight girder bridges, a two-dimensional spine-beam model with linear elastic analysis is used; the girder is modeled with elastic beam-column elements.

MR-05, structural system: A single span is a simply supported system; a structure made continuous after erection is analyzed as the completed continuous system, without modeling the system transformation during construction stages; a cast-in-place continuous girder with piers is analyzed as a continuous girder supported on piers. models_pier_columns means that the instance gives the pier column geometry and the pier columns are to be modeled; when intermediate support lines are merely called "piers" and the description gives no pier column data, the pier columns are not modeled (the pier tops act as bearing supports), and the system is continuous. (The English parenthesis in the original text is part of the implementation.)

MR-02, girder section properties: Section properties are computed by exact integration of the section geometry (outer outline minus inner voids); when several precast girders are combined into one spine beam, A and I are taken as those of the midspan section of a single interior girder multiplied by the number of girders, neglecting wet joints and diaphragms.

MR-00, input priority: Parameters explicitly given in the problem (measured elastic modulus, unit weight specified by the owner, shear modulus from the manufacturer, etc.) take precedence over the code default values.

MR-07, dead load and mass: The dead load includes only the self-weight of the girder, w = γA; the mass is m = w/g, with a consistent mass matrix.

MR-04, number of bearings and parallel combination: Bearings on the same support line act in parallel and their stiffnesses are added; for precast girders, the number of bearings = bearings per girder end × number of girders; for cast-in-place box girders, the number of bearings on each support line is used.

MR-03, modeling of laminated elastomeric bearings: Laminated elastomeric bearings are modeled as zero-length springs with vertical stiffness Kv; ordinary laminated bearings take the shear stiffness Kh longitudinally, and PTFE sliding bearings are longitudinally free (Kh = 0); rotation is free. The bearings are placed at the elevation of the girder axis.

MR-08, modeling of spherical bearings: Spherical bearings are modeled as rigid vertical supports with free rotation; fixed bearings (GD) and transversely guided bearings (DX) are restrained longitudinally, and longitudinally sliding bearings are longitudinally free.

MR-06, modeling of piers: Piers are modeled as elastic beam-column elements fixed at the base; two-column piers are merged into one column, with A and I taken as the sums over the columns; the mass of the pier is included.

LL-01, lane load arrangement: qk is applied over the influence-line segments of the same sign; Pk is placed at the most unfavorable ordinate of the influence line and is determined from the calculated span of the span in which it lies; the effects are multiplied by (1 + μ), the number of design lanes, and the transverse lane reduction factor.

LL-02, fundamental frequency used for the impact factor: The impact factor is computed from the fundamental frequency of the structure according to Clause 4.3.2 of JTG D60-2015, and the fundamental frequency is taken as the first vertical bending frequency from the FE modal analysis.

JTG3362-3.1.5 (JTG 3362-2018, 3.1.5, Table 3.1.5), elastic modulus of concrete by grade.

JTGD60-4.2.1 (JTG D60-2015, 4.2.1, Table 4.2.1), unit weight of materials. Note: reinforced concrete and prestressed concrete 25.0–26.0 kN/m3; the upper value of 26.0 is used for prestressed concrete.

JTG3362-8.7-S (JTG 3362-2018, 8.7), shape factor of laminated elastomeric bearings.

JTG3362-8.7-Kv (JTG 3362-2018, 8.7), vertical stiffness of laminated elastomeric bearings. Note: Ee = 5.4 Ge S^2, Eb = 2000 MPa; Kv in kN/m (a, b, and te in m, moduli in MPa).

JTG3362-8.7-Kh (JTG 3362-2018, 8.7), shear stiffness of laminated elastomeric bearings.

JTG3362-8.7-Ge (JTG 3362-2018, 8.7), standard value of the shear modulus of rubber.

JTT854 (JT/T 854-2013), spherical bearings for highway bridges. Note: GD fixed, DX unidirectionally sliding, SX bidirectionally sliding; the vertical compressive deformation is small, so the bearing may be treated as a rigid support.

JTGD60-4.3.1-lanes (JTG D60-2015, 4.3.1, Table 4.3.1-4), number of design lanes.

JTGD60-4.3.1-xi (JTG D60-2015, 4.3.1, Table 4.3.1-5), transverse lane reduction factor.

JTGD60-4.3.1-qk (JTG D60-2015, 4.3.1), characteristic value of the uniformly distributed lane load.

JTGD60-4.3.1-Pk (JTG D60-2015, 4.3.1), characteristic value of the concentrated lane load.

JTGD60-4.3.2 (JTG D60-2015, 4.3.2), impact factor of vehicle loads.
