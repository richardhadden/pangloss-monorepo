"""CIDOC CRM 7.1.3: generated from crm.rdfs by `pangloss rdf generate-ontology`. Do not edit."""

from pangloss_rdf.fields import OntologyProperty, register_ontology_prefix

register_ontology_prefix("crm", "http://www.cidoc-crm.org/cidoc-crm/")


class E1_CRM_Entity:
    """Scope note: This class comprises all things in the universe of discourse of the CIDOC Conceptual Reference Model. It is an abstract concept providing for three general properties: - Identification by name or appellation, and in particular by a preferred identifier - Classification by type, allowing further refinement of the specific subclass to which an instance belongs - Attachment of free text…"""

    _rdf_uri = "http://www.cidoc-crm.org/cidoc-crm/E1_CRM_Entity"


class E2_Temporal_Entity(E1_CRM_Entity):
    """Scope note: This class comprises all phenomena, such as the instances of E4 Periods and E5 Events, which happen over a limited extent in time. This extent in time must be contiguous, i.e., without gaps. In case the defining kinds of phenomena for an instance of E2 Temporal Entity cease to happen, and occur later again at another time, we regard that the former instance of E2 Temporal Entity has…"""

    _rdf_uri = "http://www.cidoc-crm.org/cidoc-crm/E2_Temporal_Entity"


class E52_Time_Span(E1_CRM_Entity):
    """Scope note: This class comprises abstract temporal extents, in the sense of Galilean physics, having a beginning, an end, and a duration. Instances of E52 Time-Span have no semantic connotations about phenomena happening within the temporal extent they represent. They do not convey any meaning other than a positioning on the “time-line” of chronology. The actual extent of an instance of E52…"""

    _rdf_uri = "http://www.cidoc-crm.org/cidoc-crm/E52_Time-Span"


class E53_Place(E1_CRM_Entity):
    """Scope note: This class comprises extents in the natural space where people live, in particular on the surface of the Earth, in the pure sense of physics: independent from temporal phenomena and matter. They may serve describing the physical location of things or phenomena or other areas of interest. Geometrically, instances of E53 Place constitute single contiguous areas or a finite aggregation…"""

    _rdf_uri = "http://www.cidoc-crm.org/cidoc-crm/E53_Place"


class E54_Dimension(E1_CRM_Entity):
    """Scope note: This class comprises quantifiable properties that can be measured by some calibrated means and can be approximated by values, i.e. points or regions in a mathematical or conceptual space, such as natural or real numbers, RGB values, etc. An instance of E54 Dimension represents the empirical or theoretically derived quantity, including the precision tolerances resulting from the…"""

    _rdf_uri = "http://www.cidoc-crm.org/cidoc-crm/E54_Dimension"


class E77_Persistent_Item(E1_CRM_Entity):
    """Scope note: This class comprises items that have persistent characteristics of structural nature substantially related to their identity and their integrity, sometimes known as “endurants” in philosophy. Persistent Items may be physical entities, such as people, animals or things, conceptual entities such as ideas, concepts, products of the imagination or even names. Instances of E77 Persistent…"""

    _rdf_uri = "http://www.cidoc-crm.org/cidoc-crm/E77_Persistent_Item"


class E92_Spacetime_Volume(E1_CRM_Entity):
    """Scope note: This class comprises 4-dimensional point sets (volumes) in physical spacetime (in contrast to mathematical models of it) regardless of their true geometric forms. They may derive their identity from being the extent of a material phenomenon or from being the interpretation of an expression defining an extent in spacetime. Intersections of instances of E92 Spacetime Volume, E53 Place,…"""

    _rdf_uri = "http://www.cidoc-crm.org/cidoc-crm/E92_Spacetime_Volume"


class E39_Actor(E77_Persistent_Item):
    """Scope note: This class comprises people, either individually or in groups, who have the potential to perform intentional actions of kinds for which they can be held responsible. Examples: - London and Continental Railways (E74) - the Governor of the Bank of England in 1975 (E21) - Sir Ian McKellen (E21) (Gibson, 1986) In First Order Logic: - E39(x) ⇒ E77(x)"""

    _rdf_uri = "http://www.cidoc-crm.org/cidoc-crm/E39_Actor"


class E3_Condition_State(E2_Temporal_Entity):
    """Scope note: This class comprises the states of objects characterised by a certain condition over a time-span. An instance of this class describes the prevailing physical condition of any material object or feature during a specific instance of E52 Time-Span. In general, the time-span for which a certain condition can be asserted may be shorter than the real time-span, for which this condition…"""

    _rdf_uri = "http://www.cidoc-crm.org/cidoc-crm/E3_Condition_State"


class E4_Period(E2_Temporal_Entity, E92_Spacetime_Volume):
    """Scope note: This class comprises sets of coherent phenomena or cultural manifestations occurring in time and space. It is the social or physical coherence of these phenomena that identify an instance of E4 Period and not the associated spatiotemporal extent. This extent is only the “ground” or space in an abstract physical sense that the actual process of growth, spread and retreat has covered.…"""

    _rdf_uri = "http://www.cidoc-crm.org/cidoc-crm/E4_Period"


class E70_Thing(E77_Persistent_Item):
    """Scope note: This general class comprises discrete, identifiable, instances of E77 Persistent Item that are documented as single units, that either consist of matter or depend on being carried by matter and are characterized by relative stability. They may be intellectual products or physical things. They may, for instance, have a solid physical form, an electronic encoding, or they may be a…"""

    _rdf_uri = "http://www.cidoc-crm.org/cidoc-crm/E70_Thing"


class E93_Presence(E92_Spacetime_Volume):
    """Scope note: This class comprises instances of E92 Spacetime Volume, whose temporal extent has been chosen in order to determine the spatial extent of a phenomenon over the chosen time-span. Respective phenomena may, for instance, be historical events or periods, but can also be the diachronic extent and existence of physical things. In other words, instances of this class fix a slice of another…"""

    _rdf_uri = "http://www.cidoc-crm.org/cidoc-crm/E93_Presence"


class E97_Monetary_Amount(E54_Dimension):
    """Scope note: This class comprises quantities of monetary possessions or obligations in terms of their nominal value with respect to a particular currency. These quantities may be abstract accounting units, the nominal value of a heap of coins or bank notes at the time of validity of the respective currency, the nominal value of a bill of exchange or other documents expressing monetary claims or…"""

    _rdf_uri = "http://www.cidoc-crm.org/cidoc-crm/E97_Monetary_Amount"


class E5_Event(E4_Period):
    """Scope note: This class comprises distinct, delimited and coherent processes and interactions of a material nature, in cultural, social or physical systems, involving and affecting instances of E77 Persistent Item in a way characteristic of the kind of process. Typical examples are meetings, births, deaths, actions of decision taking, making or inventing things, but also more complex and extended…"""

    _rdf_uri = "http://www.cidoc-crm.org/cidoc-crm/E5_Event"


class E71_Human_Made_Thing(E70_Thing):
    """Scope note: This class comprises discrete, identifiable human-made items that are documented as single units. These items are either intellectual products or human-made physical things, and are characterized by relative stability. They may, for instance, have a solid physical form, an electronic encoding, or they may be logical concepts or structures. Examples: - Beethoven’s 5(th) Symphony (E73)…"""

    _rdf_uri = "http://www.cidoc-crm.org/cidoc-crm/E71_Human-Made_Thing"


class E72_Legal_Object(E70_Thing):
    """Scope note: This class comprises those material or immaterial items to which instances of E30 Right, such as the right of ownership or use, can be applied. This is generally true for all instances of E18 Physical Thing. In the case of instances of E28 Conceptual Object, however, the identity of an instance of E28 Conceptual Object or the method of its use may be too ambiguous to reliably…"""

    _rdf_uri = "http://www.cidoc-crm.org/cidoc-crm/E72_Legal_Object"


class E74_Group(E39_Actor):
    """Scope note: This class comprises any gatherings or organizations of human individuals or groups that act collectively or in a similar way due to any form of unifying relationship. In the wider sense this class also comprises official positions which used to be regarded in certain contexts as one actor, independent of the current holder of the office, such as the president of a country. In such…"""

    _rdf_uri = "http://www.cidoc-crm.org/cidoc-crm/E74_Group"


class E18_Physical_Thing(E72_Legal_Object):
    """Scope note: This class comprises all persistent physical items with a relatively stable form, human-made or natural. Depending on the existence of natural boundaries of such things, the CIDOC CRM distinguishes the instances of E19 Physical Object from instances of E26 Physical Feature, such as holes, rivers, pieces of land, etc. Most instances of E19 Physical Object can be moved (if not too…"""

    _rdf_uri = "http://www.cidoc-crm.org/cidoc-crm/E18_Physical_Thing"


class E28_Conceptual_Object(E71_Human_Made_Thing):
    """Scope note: This class comprises non-material products of our minds and other human produced data that have become objects of a discourse about their identity, circumstances of creation, or historical implication. The production of such information might have been supported by the use of technical devices such as cameras or computers. Characteristically, instances of this class are created,…"""

    _rdf_uri = "http://www.cidoc-crm.org/cidoc-crm/E28_Conceptual_Object"


class E63_Beginning_of_Existence(E5_Event):
    """Scope note: This class comprises events that bring into existence any instance of E77 Persistent Item. It may be used for temporal reasoning about things (intellectual products, physical items, groups of people, living beings) beginning to exist; it serves as a hook for both a terminus post quem and a terminus ante quem. Examples: - the birth of my child (E67) (fictitious) - the birth of Snoopy,…"""

    _rdf_uri = "http://www.cidoc-crm.org/cidoc-crm/E63_Beginning_of_Existence"


class E64_End_of_Existence(E5_Event):
    """Scope note: This class comprises events that end the existence of any instance of E77 Persistent Item. It may be used for temporal reasoning about things (physical items, groups of people, living beings) ceasing to exist; it serves as a hook both a terminus post quem and a terminus ante quem. In cases where substance from an instance of E77 Persistent Item continues to exist in a new form, the…"""

    _rdf_uri = "http://www.cidoc-crm.org/cidoc-crm/E64_End_of_Existence"


class E7_Activity(E5_Event):
    """Scope note: This class comprises actions intentionally carried out by instances of E39 Actor that result in changes of state in the cultural, social, or physical systems documented. This notion includes complex, composite, and long-lasting actions such as the building of a settlement or a war, as well as simple, short-lived actions such as the opening of a door. Examples: - the Battle of…"""

    _rdf_uri = "http://www.cidoc-crm.org/cidoc-crm/E7_Activity"


class E10_Transfer_of_Custody(E7_Activity):
    """Scope note: This class comprises transfers of the physical custody or the legal responsibility for the physical custody of objects. The recording of the donor or recipient is optional. It is possible that in an instance of E10 Transfer of Custody there is either no donor or no recipient. Depending on the circumstances, it may describe: 1. the beginning of custody (there is no previous custodian)…"""

    _rdf_uri = "http://www.cidoc-crm.org/cidoc-crm/E10_Transfer_of_Custody"


class E11_Modification(E7_Activity):
    """Scope note: This class comprises instances of E7 Activity that are undertaken to create, alter or change instances of E24 Physical Human-Made Thing. This class includes the production of an item from raw materials and other so far undocumented objects. It also includes the conservation treatment of an object. Since the distinction between modification and production is not always clear,…"""

    _rdf_uri = "http://www.cidoc-crm.org/cidoc-crm/E11_Modification"


class E13_Attribute_Assignment(E7_Activity):
    """Scope note: This class comprises the actions of making assertions about one property of an object or any single relation between two items or concepts. The type of the property asserted to hold between two items or concepts can be described by the property P177 assigned property of type (is type of property assigned): E55 Type. For example, the class describes the actions of people making…"""

    _rdf_uri = "http://www.cidoc-crm.org/cidoc-crm/E13_Attribute_Assignment"


class E19_Physical_Object(E18_Physical_Thing):
    """Scope note: This class comprises items of a material nature that are units for documentation and have physical boundaries that separate them completely in an objective way from other objects. The class also includes all aggregates of objects made for functional purposes of whatever kind, independent of physical coherence, such as a set of chessmen. Typically, instances of E19 Physical Object can…"""

    _rdf_uri = "http://www.cidoc-crm.org/cidoc-crm/E19_Physical_Object"


class E24_Physical_Human_Made_Thing(E18_Physical_Thing, E71_Human_Made_Thing):
    """Scope note: This class comprises all persistent physical items of any size that are purposely created by human activity. This class comprises, besides others, human-made objects, such as a sword, and human-made features, such as rock art. For example, a “cup and ring” carving on bedrock is regarded as instance of E24 Physical Human-Made Thing. Instances of E24 Physical Human-Made Thing may be the…"""

    _rdf_uri = "http://www.cidoc-crm.org/cidoc-crm/E24_Physical_Human-Made_Thing"


class E26_Physical_Feature(E18_Physical_Thing):
    """Scope note: This class comprises identifiable features that are physically attached in an integral way to particular physical objects. Instances of E26 Physical Feature share many of the attributes of instances of E19 Physical Object. They may have a one-dimensional, two-dimensional, or three-dimensional geometric extent, but there are no natural borders that separate them completely in an…"""

    _rdf_uri = "http://www.cidoc-crm.org/cidoc-crm/E26_Physical_Feature"


class E55_Type(E28_Conceptual_Object):
    """Scope note: This class comprises concepts denoted by terms from thesauri and controlled vocabularies used to characterize and classify instances of CIDOC CRM classes. Instances of E55 Type represent concepts, in contrast to instances of E41 Appellation which are used to name instances of CIDOC CRM classes. E55 Type provides an interface to domain specific ontologies and thesauri. These can be…"""

    _rdf_uri = "http://www.cidoc-crm.org/cidoc-crm/E55_Type"


class E65_Creation(E63_Beginning_of_Existence, E7_Activity):
    """Scope note: This class comprises events that result in the creation of conceptual items or immaterial products, such as legends, poems, texts, music, images, movies, laws, types, etc. Examples: - the framing of the U.S. Constitution (Farrand, 1913) - the drafting of U.N. Resolution 1441 (United Nations Security Council, 2002) In First Order Logic: - E65(x) ⇒ E7(x) - E65(x) ⇒ E63(x)"""

    _rdf_uri = "http://www.cidoc-crm.org/cidoc-crm/E65_Creation"


class E66_Formation(E63_Beginning_of_Existence, E7_Activity):
    """Scope note: This class comprises events that result in the formation of a formal or informal E74 Group of people, such as a club, society, association, corporation, or nation. E66 Formation does not include the arbitrary aggregation of people who do not act as a collective. The formation of an instance of E74 Group does not require that the group is populated with members at the time of…"""

    _rdf_uri = "http://www.cidoc-crm.org/cidoc-crm/E66_Formation"


class E67_Birth(E63_Beginning_of_Existence):
    """Scope note: This class comprises the births of human beings. E67 Birth is a biological event focussing on the context of people coming into life. (E63 Beginning of Existence comprises the coming into life of any living being.) Twins, triplets, etc. are brought into life by the same instance of E67 Birth. The introduction of the E67 Birth event as a documentation element allows the description of…"""

    _rdf_uri = "http://www.cidoc-crm.org/cidoc-crm/E67_Birth"


class E68_Dissolution(E64_End_of_Existence):
    """Scope note: This class comprises the events that result in the formal or informal termination of an instance of E74 Group. If the dissolution was deliberate, the Dissolution event should also be instantiated as an instance of E7 Activity. Examples: - the fall of the Roman Empire (Whittington, 1964) - the liquidation of Enron Corporation (Atlas, 2001) In First Order Logic: - E68(x) ⇒ E64(x)"""

    _rdf_uri = "http://www.cidoc-crm.org/cidoc-crm/E68_Dissolution"


class E69_Death(E64_End_of_Existence):
    """Scope note: This class comprises the deaths of human beings. If a person is killed, their death should be instantiated as E69 Death and as E7 Activity. The death or perishing of other living beings should be documented as instances of E64 End of Existence. Examples: - the murder of Julius Caesar (E69, E7) (Irwin, 1935) - the death of Senator Paul Wellstone (Monast and Tao, 2002) In First Order…"""

    _rdf_uri = "http://www.cidoc-crm.org/cidoc-crm/E69_Death"


class E6_Destruction(E64_End_of_Existence):
    """Scope note: This class comprises events that destroy one or more instances of E18 Physical Thing, such that they lose their identity as the subjects of documentation. Some destruction events are intentional, while others are independent of human activity. Intentional destruction can be documented by classifying the event as both an instance of E6 Destruction and of E7 Activity. The decision to…"""

    _rdf_uri = "http://www.cidoc-crm.org/cidoc-crm/E6_Destruction"


class E81_Transformation(E63_Beginning_of_Existence, E64_End_of_Existence):
    """Scope note: This class comprises the events that result in the simultaneous destruction of one or more than one E18 Physical Thing and the creation of one or more than one E18 Physical Thing that preserves recognizable substance and structure from the first one(s) but has fundamentally different nature or identity. Although the old and the new instances of E18 Physical Thing are treated as…"""

    _rdf_uri = "http://www.cidoc-crm.org/cidoc-crm/E81_Transformation"


class E85_Joining(E7_Activity):
    """Scope note: This class comprises the activities that result in an instance of E39 Actor becoming a member of an instance of E74 Group. This class does not imply initiative by either party. It may be the initiative of a third party. Typical scenarios include becoming a member of a social organisation, becoming an employee of a company, marriage, the adoption of a child by a family, and the…"""

    _rdf_uri = "http://www.cidoc-crm.org/cidoc-crm/E85_Joining"


class E86_Leaving(E7_Activity):
    """Scope note: This class comprises the activities that result in an instance of E39 Actor to be disassociated from an instance of E74 Group. This class does not imply initiative by either party. It may be the initiative of a third party. Typical scenarios include the termination of membership in a social organisation, ending the employment at a company, divorce, and the end of tenure of somebody in…"""

    _rdf_uri = "http://www.cidoc-crm.org/cidoc-crm/E86_Leaving"


class E87_Curation_Activity(E7_Activity):
    """Scope note: This class comprises the activities that contribute to the management and the preservation and evolution of instances of E78 Curated Holding, following an implicit or explicit curation plan. It specializes the notion of activity into the curation of a collection and allows the history of curation to be recorded. Items are accumulated and organized following criteria such as subject,…"""

    _rdf_uri = "http://www.cidoc-crm.org/cidoc-crm/E87_Curation_Activity"


class E89_Propositional_Object(E28_Conceptual_Object):
    """Scope note: This class comprises immaterial items, including but not limited to stories, plots, procedural prescriptions, algorithms, laws of physics or images that are, or represent in some sense, sets of propositions about real or imaginary things and that are documented as single units or serve as topic of discourse. This class also comprises items that are “about” something in the sense of a…"""

    _rdf_uri = "http://www.cidoc-crm.org/cidoc-crm/E89_Propositional_Object"


class E8_Acquisition(E7_Activity):
    """Scope note: This class comprises transfers of legal ownership from one or more instances of E39 Actor to one or more other instances of E39 Actor. The class also applies to the establishment or loss of ownership of instances of E18 Physical Thing. It does not, however, imply changes of any other kinds of rights. The recording of the donor and/or recipient is optional. It is possible that in an…"""

    _rdf_uri = "http://www.cidoc-crm.org/cidoc-crm/E8_Acquisition"


class E90_Symbolic_Object(E28_Conceptual_Object, E72_Legal_Object):
    """Scope note: This class comprises identifiable symbols and any aggregation of symbols, such as characters, identifiers, traffic signs, emblems, texts, data sets, images, musical scores, multimedia objects, computer program code, or mathematical formulae that have an objectively recognizable structure and that are documented as single units. It includes sets of signs of any nature, which may serve…"""

    _rdf_uri = "http://www.cidoc-crm.org/cidoc-crm/E90_Symbolic_Object"


class E9_Move(E7_Activity):
    """Scope note: This class comprises changes of the physical location of the instances of E19 Physical Object. Note, that the class E9 Move inherits the property P7 took place at (witnessed): E53 Place. This property should be used to describe the trajectory or a larger area within which a move takes place, whereas the properties P26 moved to (was destination of), P27 moved from (was origin of)…"""

    _rdf_uri = "http://www.cidoc-crm.org/cidoc-crm/E9_Move"


class E12_Production(E11_Modification, E63_Beginning_of_Existence):
    """Scope note: This class comprises activities that are designed to, and succeed in, creating one or more new items. It specializes the notion of modification into production. The decision as to whether or not an object is regarded as new is context sensitive. Normally, items are considered “new” if there is no obvious overall similarity between them and the consumed items and material used in their…"""

    _rdf_uri = "http://www.cidoc-crm.org/cidoc-crm/E12_Production"


class E14_Condition_Assessment(E13_Attribute_Assignment):
    """Scope note: This class describes the act of assessing the state of preservation of an object during a particular period. The condition assessment may be carried out by inspection, measurement, or through historical research. This class is used to document circumstances of the respective assessment that is relevant to interpret its quality at a later stage, or to continue research on related…"""

    _rdf_uri = "http://www.cidoc-crm.org/cidoc-crm/E14_Condition_Assessment"


class E15_Identifier_Assignment(E13_Attribute_Assignment):
    """Scope note: This class comprises activities that result in the allocation of an identifier to an instance of E1 CRM Entity. An instance of E15 Identifier Assignment may include the creation of the identifier from multiple constituents, which themselves may be instances of E41 Appellation. The syntax and kinds of constituents to be used may be declared in a rule constituting an instance of E29…"""

    _rdf_uri = "http://www.cidoc-crm.org/cidoc-crm/E15_Identifier_Assignment"


class E16_Measurement(E13_Attribute_Assignment):
    """Scope note: This class comprises actions measuring physical properties and other values that can be determined by a systematic, objective procedure of direct observation of particular states of physical reality. An instance of E16 Measurement may use simple counting or tools, such as yardsticks or radiation detection devices. The interest is in the method and care applied, so that the reliability…"""

    _rdf_uri = "http://www.cidoc-crm.org/cidoc-crm/E16_Measurement"


class E17_Type_Assignment(E13_Attribute_Assignment):
    """Scope note: This class comprises the actions of classifying items of whatever kind. Such items include objects, specimens, people, actions, and concepts. This class allows for the documentation of the context of classification acts in cases where the value of the classification depends on the personal opinion of the classifier, and the date that the classification was made. This class also…"""

    _rdf_uri = "http://www.cidoc-crm.org/cidoc-crm/E17_Type_Assignment"


class E20_Biological_Object(E19_Physical_Object):
    """Scope note: This class comprises individual items of a material nature, which live, have lived, or are natural products of or from living organisms. Artificial objects that incorporate biological elements, such as Victorian butterfly frames, can be documented as both instances of E20 Biological Object and E22 Human-Made Object. Examples: - me (fictitious) - Tut-Ankh-Amun (Edwards and Boltin,…"""

    _rdf_uri = "http://www.cidoc-crm.org/cidoc-crm/E20_Biological_Object"


class E22_Human_Made_Object(E19_Physical_Object, E24_Physical_Human_Made_Thing):
    """Scope note: This class comprises all persistent physical objects of any size that are purposely created by human activity and have physical boundaries that separate them completely in an objective way from other objects. The class also includes all aggregates of objects made for functional purposes of whatever kind, independent of physical coherence, such as a set of chessmen. Examples: - the…"""

    _rdf_uri = "http://www.cidoc-crm.org/cidoc-crm/E22_Human-Made_Object"


class E25_Human_Made_Feature(E24_Physical_Human_Made_Thing, E26_Physical_Feature):
    """Scope note: This class comprises physical features that are purposely created by human activity, such as scratches, artificial caves, artificial water channels, etc. In particular, it includes the information encoding features on mechanical or digital carriers. Examples: - the Manchester Ship Canal (Farnie, 1980) - Michael Jackson’s nose following plastic surgery - the laser-readable “pits”…"""

    _rdf_uri = "http://www.cidoc-crm.org/cidoc-crm/E25_Human-Made_Feature"


class E27_Site(E26_Physical_Feature):
    """Scope note: This class comprises pieces of land or sea floor. In contrast to the purely geometric notion of E53 Place, this class describes constellations of matter on the surface of the Earth or other celestial body, which can be represented by photographs, paintings, and maps. Instances of E27 Site are composed of relatively immobile material items and features in a particular configuration at…"""

    _rdf_uri = "http://www.cidoc-crm.org/cidoc-crm/E27_Site"


class E30_Right(E89_Propositional_Object):
    """Scope note: This class comprises legal privileges concerning material and immaterial things or their derivatives. These include reproduction and property rights. Examples: - copyright held by ISO on ISO/CD 21127 - ownership of the “Mona Lisa” by the museum of the Louvre, Paris, France In First Order Logic: - E30(x) ⇒ E89(x)"""

    _rdf_uri = "http://www.cidoc-crm.org/cidoc-crm/E30_Right"


class E41_Appellation(E90_Symbolic_Object):
    """Scope note: This class comprises all signs, either meaningful or not, or arrangements of signs following a specific syntax, that are used or can be used to refer to and identify a specific instance of some class within a certain context. Instances of E41 Appellation do not identify things by their meaning, even if they happen to have one, but by convention, tradition, or agreement. Instances of…"""

    _rdf_uri = "http://www.cidoc-crm.org/cidoc-crm/E41_Appellation"


class E56_Language(E55_Type):
    """Scope note: This class is a specialization of E55 Type and comprises the natural languages in the sense of concepts. This type is used categorically in the model without reference to instances of it, i.e. the Model does not foresee the description of instances of instances of E56 Language, e.g. “instances of Mandarin Chinese”. It is recommended that internationally or nationally agreed codes and…"""

    _rdf_uri = "http://www.cidoc-crm.org/cidoc-crm/E56_Language"


class E57_Material(E55_Type):
    """Scope note: This class is a specialization of E55 Type and comprises the concepts of materials. Instances of E57 Material may denote properties of matter before its use, during its use, and as incorporated in an object, such as ultramarine powder, tempera paste, reinforced concrete. Discrete pieces of raw-materials kept in museums, such as bricks, sheets of fabric, pieces of metal, should be…"""

    _rdf_uri = "http://www.cidoc-crm.org/cidoc-crm/E57_Material"


class E58_Measurement_Unit(E55_Type):
    """Scope note: This class is a specialization of E55 Type and comprises the types of measurement units: feet, inches, centimetres, litres, lumens, etc. This type is used categorically in the model without reference to instances of it, i.e. the model does not foresee the description of instances of instances of E58 Measurement Unit, e.g. “instances of cm”. Système International (SI) units or…"""

    _rdf_uri = "http://www.cidoc-crm.org/cidoc-crm/E58_Measurement_Unit"


class E73_Information_Object(E89_Propositional_Object, E90_Symbolic_Object):
    """Scope note: This class comprises identifiable immaterial items, such as poems, jokes, data sets, images, texts, multimedia objects, procedural prescriptions, computer program code, algorithm or mathematical formulae, that have an objectively recognizable structure and are documented as single units. The encoding structure known as a “named graph” also falls under this class, so that each “named…"""

    _rdf_uri = "http://www.cidoc-crm.org/cidoc-crm/E73_Information_Object"


class E78_Curated_Holding(E24_Physical_Human_Made_Thing):
    """Scope note: This class comprises aggregations of instances of E18 Physical Thing that are assembled and maintained (“curated” and “preserved,” in museological terminology) by one or more instances of E39 Actor over time for a specific purpose and audience, and according to a particular collection development plan. Typical instances of curated holdings are museum collections, archives, library…"""

    _rdf_uri = "http://www.cidoc-crm.org/cidoc-crm/E78_Curated_Holding"


class E79_Part_Addition(E11_Modification):
    """Scope note: This class comprises activities that result in an instance of E18 Physical Thing being increased, enlarged, or augmented by the addition of a part. Typical scenarios include the attachment of an accessory, the integration of a component, the addition of an element to an aggregate object, or the accessioning of an object into a curated instance of E78 Curated Holding. Both the E18…"""

    _rdf_uri = "http://www.cidoc-crm.org/cidoc-crm/E79_Part_Addition"


class E80_Part_Removal(E11_Modification):
    """Scope note: This class comprises the activities that result in an instance of E18 Physical Thing being decreased by the removal of a part. Typical scenarios include the detachment of an accessory, the removal of a component or part of a composite object, or the deaccessioning of an object from a curated collection, an instance of E78 Curated Holding. If the instance of E80 Part Removal results in…"""

    _rdf_uri = "http://www.cidoc-crm.org/cidoc-crm/E80_Part_Removal"


class E83_Type_Creation(E65_Creation):
    """Scope note: This class comprises activities formally defining new types of items. It is typically a rigorous scholarly or scientific process that ensures a type is exhaustively described and appropriately named. In some cases, particularly in archaeology and the life sciences, E83 Type Creation requires the identification of an exemplary specimen and the publication of the type definition in an…"""

    _rdf_uri = "http://www.cidoc-crm.org/cidoc-crm/E83_Type_Creation"


class E96_Purchase(E8_Acquisition):
    """Scope note: This class comprises transfers of legal ownership from one or more instances of E39 Actor to one or more different instances of E39 Actor, where the transferring party is completely compensated by the payment of a monetary amount. In more detail, a purchase agreement establishes a fixed monetary obligation at its initialization on the receiving party, to the giving party. An instance…"""

    _rdf_uri = "http://www.cidoc-crm.org/cidoc-crm/E96_Purchase"


class E99_Product_Type(E55_Type):
    """Scope note: This class comprises types that stand as the models for instances of E22 Human-Made Object that are produced as the result of production activities using plans exact enough to result in one or more series of uniform, functionally and aesthetically identical and interchangeable items. The product type is the intended ideal form of the manufacture process. It is typical of instances of…"""

    _rdf_uri = "http://www.cidoc-crm.org/cidoc-crm/E99_Product_Type"


class E21_Person(E20_Biological_Object, E39_Actor):
    """Scope note: This class comprises real persons who live or are assumed to have lived. Legendary figures that may have existed, such as Ulysses and King Arthur, fall into this class if the documentation refers to them as historical figures. In cases where doubt exists as to whether several persons are in fact identical, multiple instances can be created and linked to indicate their relationship.…"""

    _rdf_uri = "http://www.cidoc-crm.org/cidoc-crm/E21_Person"


class E29_Design_or_Procedure(E73_Information_Object):
    """Scope note: This class comprises documented plans for the execution of actions in order to achieve a result of a specific quality, form, or contents. In particular, it comprises plans for deliberate human activities that may result in new instances of E71 Human-Made Thing or for shaping or guiding the execution of an instance of E7 Activity. Instances of E29 Design or Procedure can be structured…"""

    _rdf_uri = "http://www.cidoc-crm.org/cidoc-crm/E29_Design_or_Procedure"


class E31_Document(E73_Information_Object):
    """Scope note: This class comprises identifiable immaterial items that make propositions about reality. These propositions may be expressed in text, graphics, images, audiograms, videograms, or by other similar means. Documentation databases are regarded as instances of E31 Document. This class should not be confused with the concept “document” in Information Technology, which is compatible with E73…"""

    _rdf_uri = "http://www.cidoc-crm.org/cidoc-crm/E31_Document"


class E33_Linguistic_Object(E73_Information_Object):
    """Scope note: This class comprises identifiable expressions in natural language or languages. Instances of E33 Linguistic Object can be expressed in many ways: e.g. as written texts, recorded speech, or sign language. However, the CIDOC CRM treats instances of E33 Linguistic Object independently from the medium or method by which they are expressed. Expressions in formal languages, such as computer…"""

    _rdf_uri = "http://www.cidoc-crm.org/cidoc-crm/E33_Linguistic_Object"


class E36_Visual_Item(E73_Information_Object):
    """Scope note: This class comprises the intellectual or conceptual aspects of recognisable marks and images. This class does not intend to describe the idiosyncratic characteristics of an individual physical embodiment of a visual item, but the underlying prototype. For example, a mark such as the ICOM logo is generally considered to be the same logo when used on any number of publications. The…"""

    _rdf_uri = "http://www.cidoc-crm.org/cidoc-crm/E36_Visual_Item"


class E42_Identifier(E41_Appellation):
    """Scope note: This class comprises strings or codes assigned to instances of E1 CRM Entity in order to identify them uniquely and permanently within the context of one or more organisations. Such codes are often known as inventory numbers, registration codes, etc. and are typically composed of alphanumeric sequences. Postal addresses, telephone numbers, URLs and e-mail addresses are characteristic…"""

    _rdf_uri = "http://www.cidoc-crm.org/cidoc-crm/E42_Identifier"


class E98_Currency(E58_Measurement_Unit):
    """Scope note: This class comprises the units in which a monetary system, supported by an administrative authority or other community, quantifies and arithmetically compares all monetary amounts declared in the unit. The unit of a monetary system must describe a nominal value which is kept constant by its administrative authority and an associated banking system if it exists, and not by market…"""

    _rdf_uri = "http://www.cidoc-crm.org/cidoc-crm/E98_Currency"


class E32_Authority_Document(E31_Document):
    """Scope note: This class comprises encyclopaedia, thesauri, authority lists and other documents that define terminology or conceptual systems for consistent use. Examples: - Webster's Dictionary (Herbert, 1994) - Getty Art and Architecture Thesaurus (Getty Trust, 1990) - the CIDOC Conceptual Reference Model (Gergatsoulis et al., 2010) In First Order Logic: - E32(x) ⇒ E31(x)"""

    _rdf_uri = "http://www.cidoc-crm.org/cidoc-crm/E32_Authority_Document"


class E33_E41_Linguistic_Appellation(E33_Linguistic_Object, E41_Appellation):
    _rdf_uri = "http://www.cidoc-crm.org/cidoc-crm/E33_E41_Linguistic_Appellation"


class E35_Title(E33_Linguistic_Object, E41_Appellation):
    """Scope note: This class comprises the textual strings that within a cultural context can be clearly identified as titles due to their form. Being a subclass of E41 Appellation, E35 Title can only be used when such a string is actually used as a title of a work, such as a text, an artwork, or a piece of music. Titles are proper noun phrases or verbal phrases, and should not be confused with generic…"""

    _rdf_uri = "http://www.cidoc-crm.org/cidoc-crm/E35_Title"


class E37_Mark(E36_Visual_Item):
    """Scope note: This class comprises symbols, signs, signatures, or short texts applied to instances of E24 Physical Human-Made Thing by arbitrary techniques, often in order to indicate such things as creator, owner, dedications, purpose, or to communicate information generally. Instances of E37 Mark do not represent the actual image of a mark, but the abstract ideal (or archetype) as used for…"""

    _rdf_uri = "http://www.cidoc-crm.org/cidoc-crm/E37_Mark"


class E34_Inscription(E33_Linguistic_Object, E37_Mark):
    """Scope note: This class comprises recognisable texts that can be attached to instances of E24 Physical Human-Made Thing. The transcription of the text can be documented in a note by P3 has note: E62 String. The alphabet used can be documented by P2 has type: E55 Type. This class is not intended to describe the idiosyncratic characteristics of an individual physical embodiment of an inscription,…"""

    _rdf_uri = "http://www.cidoc-crm.org/cidoc-crm/E34_Inscription"


P100_was_death_of = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P100_was_death_of",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E69_Death",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E21_Person",),
)
P100i_died_in = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P100i_died_in",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E21_Person",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E69_Death",),
)
P101_had_as_general_use = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P101_had_as_general_use",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E70_Thing",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E55_Type",),
)
P101i_was_use_of = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P101i_was_use_of",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E55_Type",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E70_Thing",),
)
P102_has_title = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P102_has_title",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E71_Human-Made_Thing",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E35_Title",),
)
P102i_is_title_of = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P102i_is_title_of",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E35_Title",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E71_Human-Made_Thing",),
)
P103_was_intended_for = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P103_was_intended_for",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E71_Human-Made_Thing",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E55_Type",),
)
P103i_was_intention_of = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P103i_was_intention_of",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E55_Type",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E71_Human-Made_Thing",),
)
P104_is_subject_to = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P104_is_subject_to",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E72_Legal_Object",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E30_Right",),
)
P104i_applies_to = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P104i_applies_to",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E30_Right",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E72_Legal_Object",),
)
P105_right_held_by = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P105_right_held_by",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E72_Legal_Object",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E39_Actor",),
)
P105i_has_right_on = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P105i_has_right_on",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E39_Actor",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E72_Legal_Object",),
)
P106_is_composed_of = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P106_is_composed_of",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E90_Symbolic_Object",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E90_Symbolic_Object",),
)
P106i_forms_part_of = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P106i_forms_part_of",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E90_Symbolic_Object",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E90_Symbolic_Object",),
)
P107_has_current_or_former_member = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P107_has_current_or_former_member",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E74_Group",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E39_Actor",),
)
P107i_is_current_or_former_member_of = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P107i_is_current_or_former_member_of",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E39_Actor",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E74_Group",),
)
P108_has_produced = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P108_has_produced",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E12_Production",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E24_Physical_Human-Made_Thing",),
)
P108i_was_produced_by = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P108i_was_produced_by",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E24_Physical_Human-Made_Thing",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E12_Production",),
)
P109_has_current_or_former_curator = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P109_has_current_or_former_curator",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E78_Curated_Holding",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E39_Actor",),
)
P109i_is_current_or_former_curator_of = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P109i_is_current_or_former_curator_of",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E39_Actor",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E78_Curated_Holding",),
)
P10_falls_within = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P10_falls_within",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E92_Spacetime_Volume",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E92_Spacetime_Volume",),
)
P10i_contains = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P10i_contains",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E92_Spacetime_Volume",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E92_Spacetime_Volume",),
)
P110_augmented = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P110_augmented",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E79_Part_Addition",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E18_Physical_Thing",),
)
P110i_was_augmented_by = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P110i_was_augmented_by",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E18_Physical_Thing",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E79_Part_Addition",),
)
P111_added = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P111_added",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E79_Part_Addition",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E18_Physical_Thing",),
)
P111i_was_added_by = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P111i_was_added_by",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E18_Physical_Thing",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E79_Part_Addition",),
)
P112_diminished = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P112_diminished",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E80_Part_Removal",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E18_Physical_Thing",),
)
P112i_was_diminished_by = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P112i_was_diminished_by",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E18_Physical_Thing",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E80_Part_Removal",),
)
P113_removed = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P113_removed",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E80_Part_Removal",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E18_Physical_Thing",),
)
P113i_was_removed_by = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P113i_was_removed_by",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E18_Physical_Thing",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E80_Part_Removal",),
)
P11_had_participant = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P11_had_participant",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E5_Event",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E39_Actor",),
)
P11i_participated_in = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P11i_participated_in",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E39_Actor",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E5_Event",),
)
P121_overlaps_with = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P121_overlaps_with",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E53_Place",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E53_Place",),
)
P122_borders_with = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P122_borders_with",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E53_Place",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E53_Place",),
)
P123_resulted_in = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P123_resulted_in",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E81_Transformation",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E18_Physical_Thing",),
)
P123i_resulted_from = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P123i_resulted_from",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E18_Physical_Thing",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E81_Transformation",),
)
P124_transformed = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P124_transformed",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E81_Transformation",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E18_Physical_Thing",),
)
P124i_was_transformed_by = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P124i_was_transformed_by",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E18_Physical_Thing",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E81_Transformation",),
)
P125_used_object_of_type = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P125_used_object_of_type",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E7_Activity",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E55_Type",),
)
P125i_was_type_of_object_used_in = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P125i_was_type_of_object_used_in",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E55_Type",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E7_Activity",),
)
P126_employed = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P126_employed",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E11_Modification",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E57_Material",),
)
P126i_was_employed_in = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P126i_was_employed_in",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E57_Material",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E11_Modification",),
)
P127_has_broader_term = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P127_has_broader_term",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E55_Type",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E55_Type",),
)
P127i_has_narrower_term = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P127i_has_narrower_term",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E55_Type",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E55_Type",),
)
P128_carries = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P128_carries",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E18_Physical_Thing",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E90_Symbolic_Object",),
)
P128i_is_carried_by = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P128i_is_carried_by",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E90_Symbolic_Object",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E18_Physical_Thing",),
)
P129_is_about = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P129_is_about",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E89_Propositional_Object",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E1_CRM_Entity",),
)
P129i_is_subject_of = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P129i_is_subject_of",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E1_CRM_Entity",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E89_Propositional_Object",),
)
P12_occurred_in_the_presence_of = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P12_occurred_in_the_presence_of",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E5_Event",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E77_Persistent_Item",),
)
P12i_was_present_at = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P12i_was_present_at",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E77_Persistent_Item",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E5_Event",),
)
P130_shows_features_of = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P130_shows_features_of",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E70_Thing",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E70_Thing",),
)
P130i_features_are_also_found_on = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P130i_features_are_also_found_on",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E70_Thing",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E70_Thing",),
)
P132_spatiotemporally_overlaps_with = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P132_spatiotemporally_overlaps_with",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E92_Spacetime_Volume",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E92_Spacetime_Volume",),
)
P133_is_spatiotemporally_separated_from = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P133_is_spatiotemporally_separated_from",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E92_Spacetime_Volume",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E92_Spacetime_Volume",),
)
P134_continued = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P134_continued",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E7_Activity",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E7_Activity",),
)
P134i_was_continued_by = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P134i_was_continued_by",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E7_Activity",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E7_Activity",),
)
P135_created_type = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P135_created_type",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E83_Type_Creation",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E55_Type",),
)
P135i_was_created_by = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P135i_was_created_by",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E55_Type",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E83_Type_Creation",),
)
P136_was_based_on = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P136_was_based_on",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E83_Type_Creation",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E1_CRM_Entity",),
)
P136i_supported_type_creation = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P136i_supported_type_creation",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E1_CRM_Entity",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E83_Type_Creation",),
)
P137_exemplifies = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P137_exemplifies",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E1_CRM_Entity",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E55_Type",),
)
P137i_is_exemplified_by = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P137i_is_exemplified_by",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E55_Type",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E1_CRM_Entity",),
)
P138_represents = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P138_represents",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E36_Visual_Item",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E1_CRM_Entity",),
)
P138i_has_representation = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P138i_has_representation",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E1_CRM_Entity",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E36_Visual_Item",),
)
P139_has_alternative_form = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P139_has_alternative_form",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E41_Appellation",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E41_Appellation",),
)
P139i_is_alternative_form_of = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P139i_is_alternative_form_of",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E41_Appellation",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E41_Appellation",),
)
P13_destroyed = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P13_destroyed",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E6_Destruction",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E18_Physical_Thing",),
)
P13i_was_destroyed_by = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P13i_was_destroyed_by",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E18_Physical_Thing",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E6_Destruction",),
)
P140_assigned_attribute_to = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P140_assigned_attribute_to",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E13_Attribute_Assignment",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E1_CRM_Entity",),
)
P140i_was_attributed_by = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P140i_was_attributed_by",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E1_CRM_Entity",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E13_Attribute_Assignment",),
)
P141_assigned = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P141_assigned",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E13_Attribute_Assignment",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E1_CRM_Entity",),
)
P141i_was_assigned_by = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P141i_was_assigned_by",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E1_CRM_Entity",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E13_Attribute_Assignment",),
)
P142_used_constituent = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P142_used_constituent",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E15_Identifier_Assignment",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E90_Symbolic_Object",),
)
P142i_was_used_in = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P142i_was_used_in",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E90_Symbolic_Object",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E15_Identifier_Assignment",),
)
P143_joined = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P143_joined",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E85_Joining",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E39_Actor",),
)
P143i_was_joined_by = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P143i_was_joined_by",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E39_Actor",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E85_Joining",),
)
P144_joined_with = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P144_joined_with",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E85_Joining",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E74_Group",),
)
P144i_gained_member_by = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P144i_gained_member_by",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E74_Group",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E85_Joining",),
)
P145_separated = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P145_separated",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E86_Leaving",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E39_Actor",),
)
P145i_left_by = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P145i_left_by",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E39_Actor",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E86_Leaving",),
)
P146_separated_from = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P146_separated_from",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E86_Leaving",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E74_Group",),
)
P146i_lost_member_by = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P146i_lost_member_by",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E74_Group",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E86_Leaving",),
)
P147_curated = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P147_curated",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E87_Curation_Activity",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E78_Curated_Holding",),
)
P147i_was_curated_by = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P147i_was_curated_by",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E78_Curated_Holding",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E87_Curation_Activity",),
)
P148_has_component = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P148_has_component",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E89_Propositional_Object",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E89_Propositional_Object",),
)
P148i_is_component_of = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P148i_is_component_of",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E89_Propositional_Object",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E89_Propositional_Object",),
)
P14_carried_out_by = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P14_carried_out_by",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E7_Activity",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E39_Actor",),
)
P14i_performed = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P14i_performed",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E39_Actor",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E7_Activity",),
)
P150_defines_typical_parts_of = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P150_defines_typical_parts_of",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E55_Type",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E55_Type",),
)
P150i_defines_typical_wholes_for = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P150i_defines_typical_wholes_for",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E55_Type",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E55_Type",),
)
P151_was_formed_from = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P151_was_formed_from",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E66_Formation",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E74_Group",),
)
P151i_participated_in = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P151i_participated_in",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E74_Group",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E66_Formation",),
)
P152_has_parent = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P152_has_parent",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E21_Person",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E21_Person",),
)
P152i_is_parent_of = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P152i_is_parent_of",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E21_Person",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E21_Person",),
)
P156_occupies = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P156_occupies",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E18_Physical_Thing",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E53_Place",),
)
P156i_is_occupied_by = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P156i_is_occupied_by",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E53_Place",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E18_Physical_Thing",),
)
P157_is_at_rest_relative_to = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P157_is_at_rest_relative_to",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E53_Place",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E18_Physical_Thing",),
)
P157i_provides_reference_space_for = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P157i_provides_reference_space_for",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E18_Physical_Thing",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E53_Place",),
)
P15_was_influenced_by = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P15_was_influenced_by",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E7_Activity",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E1_CRM_Entity",),
)
P15i_influenced = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P15i_influenced",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E1_CRM_Entity",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E7_Activity",),
)
P160_has_temporal_projection = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P160_has_temporal_projection",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E92_Spacetime_Volume",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E52_Time-Span",),
)
P160i_is_temporal_projection_of = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P160i_is_temporal_projection_of",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E52_Time-Span",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E92_Spacetime_Volume",),
)
P161_has_spatial_projection = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P161_has_spatial_projection",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E92_Spacetime_Volume",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E53_Place",),
)
P161i_is_spatial_projection_of = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P161i_is_spatial_projection_of",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E53_Place",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E92_Spacetime_Volume",),
)
P164_is_temporally_specified_by = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P164_is_temporally_specified_by",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E93_Presence",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E52_Time-Span",),
)
P164i_temporally_specifies = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P164i_temporally_specifies",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E52_Time-Span",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E93_Presence",),
)
P165_incorporates = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P165_incorporates",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E73_Information_Object",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E90_Symbolic_Object",),
)
P165i_is_incorporated_in = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P165i_is_incorporated_in",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E90_Symbolic_Object",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E73_Information_Object",),
)
P166_was_a_presence_of = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P166_was_a_presence_of",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E93_Presence",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E92_Spacetime_Volume",),
)
P166i_had_presence = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P166i_had_presence",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E92_Spacetime_Volume",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E93_Presence",),
)
P167_was_within = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P167_was_within",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E93_Presence",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E53_Place",),
)
P167i_includes = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P167i_includes",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E53_Place",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E93_Presence",),
)
P168_place_is_defined_by = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P168_place_is_defined_by",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E53_Place",),
    range=("http://www.w3.org/2000/01/rdf-schema#Literal",),
)
P169i_spacetime_volume_is_defined_by = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P169i_spacetime_volume_is_defined_by",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E92_Spacetime_Volume",),
    range=("http://www.w3.org/2000/01/rdf-schema#Literal",),
)
P16_used_specific_object = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P16_used_specific_object",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E7_Activity",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E70_Thing",),
)
P16i_was_used_for = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P16i_was_used_for",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E70_Thing",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E7_Activity",),
)
P170i_time_is_defined_by = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P170i_time_is_defined_by",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E52_Time-Span",),
    range=("http://www.w3.org/2000/01/rdf-schema#Literal",),
)
P171_at_some_place_within = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P171_at_some_place_within",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E53_Place",),
    range=("http://www.w3.org/2000/01/rdf-schema#Literal",),
)
P172_contains = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P172_contains",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E53_Place",),
    range=("http://www.w3.org/2000/01/rdf-schema#Literal",),
)
P173_starts_before_or_with_the_end_of = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P173_starts_before_or_with_the_end_of",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E2_Temporal_Entity",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E2_Temporal_Entity",),
)
P173i_ends_after_or_with_the_start_of = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P173i_ends_after_or_with_the_start_of",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E2_Temporal_Entity",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E2_Temporal_Entity",),
)
P174_starts_before_the_end_of = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P174_starts_before_the_end_of",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E2_Temporal_Entity",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E2_Temporal_Entity",),
)
P174i_ends_after_the_start_of = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P174i_ends_after_the_start_of",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E2_Temporal_Entity",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E2_Temporal_Entity",),
)
P175_starts_before_or_with_the_start_of = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P175_starts_before_or_with_the_start_of",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E2_Temporal_Entity",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E2_Temporal_Entity",),
)
P175i_starts_after_or_with_the_start_of = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P175i_starts_after_or_with_the_start_of",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E2_Temporal_Entity",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E2_Temporal_Entity",),
)
P176_starts_before_the_start_of = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P176_starts_before_the_start_of",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E2_Temporal_Entity",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E2_Temporal_Entity",),
)
P176i_starts_after_the_start_of = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P176i_starts_after_the_start_of",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E2_Temporal_Entity",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E2_Temporal_Entity",),
)
P177_assigned_property_of_type = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P177_assigned_property_of_type",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E13_Attribute_Assignment",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E55_Type",),
)
P177i_is_type_of_property_assigned = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P177i_is_type_of_property_assigned",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E55_Type",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E13_Attribute_Assignment",),
)
P179_had_sales_price = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P179_had_sales_price",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E96_Purchase",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E97_Monetary_Amount",),
)
P179i_was_sales_price_of = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P179i_was_sales_price_of",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E97_Monetary_Amount",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E96_Purchase",),
)
P17_was_motivated_by = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P17_was_motivated_by",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E7_Activity",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E1_CRM_Entity",),
)
P17i_motivated = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P17i_motivated",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E1_CRM_Entity",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E7_Activity",),
)
P180_has_currency = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P180_has_currency",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E97_Monetary_Amount",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E98_Currency",),
)
P180i_was_currency_of = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P180i_was_currency_of",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E98_Currency",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E97_Monetary_Amount",),
)
P182_ends_before_or_with_the_start_of = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P182_ends_before_or_with_the_start_of",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E2_Temporal_Entity",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E2_Temporal_Entity",),
)
P182i_starts_after_or_with_the_end_of = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P182i_starts_after_or_with_the_end_of",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E2_Temporal_Entity",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E2_Temporal_Entity",),
)
P183_ends_before_the_start_of = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P183_ends_before_the_start_of",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E2_Temporal_Entity",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E2_Temporal_Entity",),
)
P183i_starts_after_the_end_of = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P183i_starts_after_the_end_of",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E2_Temporal_Entity",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E2_Temporal_Entity",),
)
P184_ends_before_or_with_the_end_of = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P184_ends_before_or_with_the_end_of",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E2_Temporal_Entity",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E2_Temporal_Entity",),
)
P184i_ends_with_or_after_the_end_of = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P184i_ends_with_or_after_the_end_of",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E2_Temporal_Entity",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E2_Temporal_Entity",),
)
P185_ends_before_the_end_of = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P185_ends_before_the_end_of",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E2_Temporal_Entity",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E2_Temporal_Entity",),
)
P185i_ends_after_the_end_of = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P185i_ends_after_the_end_of",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E2_Temporal_Entity",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E2_Temporal_Entity",),
)
P186_produced_thing_of_product_type = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P186_produced_thing_of_product_type",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E12_Production",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E99_Product_Type",),
)
P186i_is_produced_by = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P186i_is_produced_by",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E99_Product_Type",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E12_Production",),
)
P187_has_production_plan = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P187_has_production_plan",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E99_Product_Type",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E29_Design_or_Procedure",),
)
P187i_is_production_plan_for = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P187i_is_production_plan_for",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E29_Design_or_Procedure",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E99_Product_Type",),
)
P188_requires_production_tool = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P188_requires_production_tool",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E99_Product_Type",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E19_Physical_Object",),
)
P188i_is_production_tool_for = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P188i_is_production_tool_for",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E19_Physical_Object",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E99_Product_Type",),
)
P189_approximates = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P189_approximates",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E53_Place",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E53_Place",),
)
P189i_is_approximated_by = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P189i_is_approximated_by",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E53_Place",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E53_Place",),
)
P190_has_symbolic_content = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P190_has_symbolic_content",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E90_Symbolic_Object",),
    range=("http://www.w3.org/2000/01/rdf-schema#Literal",),
)
P191_had_duration = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P191_had_duration",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E52_Time-Span",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E54_Dimension",),
)
P191i_was_duration_of = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P191i_was_duration_of",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E54_Dimension",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E52_Time-Span",),
)
P195_was_a_presence_of = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P195_was_a_presence_of",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E93_Presence",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E18_Physical_Thing",),
)
P195i_had_presence = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P195i_had_presence",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E18_Physical_Thing",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E93_Presence",),
)
P196_defines = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P196_defines",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E18_Physical_Thing",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E92_Spacetime_Volume",),
)
P196i_is_defined_by = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P196i_is_defined_by",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E92_Spacetime_Volume",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E18_Physical_Thing",),
)
P197_covered_parts_of = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P197_covered_parts_of",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E93_Presence",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E53_Place",),
)
P197i_was_partially_covered_by = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P197i_was_partially_covered_by",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E53_Place",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E93_Presence",),
)
P198_holds_or_supports = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P198_holds_or_supports",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E18_Physical_Thing",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E18_Physical_Thing",),
)
P198i_is_held_or_supported_by = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P198i_is_held_or_supported_by",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E18_Physical_Thing",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E18_Physical_Thing",),
)
P19_was_intended_use_of = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P19_was_intended_use_of",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E7_Activity",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E71_Human-Made_Thing",),
)
P19i_was_made_for = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P19i_was_made_for",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E71_Human-Made_Thing",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E7_Activity",),
)
P1_is_identified_by = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P1_is_identified_by",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E1_CRM_Entity",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E41_Appellation",),
)
P1i_identifies = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P1i_identifies",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E41_Appellation",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E1_CRM_Entity",),
)
P20_had_specific_purpose = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P20_had_specific_purpose",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E7_Activity",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E5_Event",),
)
P20i_was_purpose_of = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P20i_was_purpose_of",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E5_Event",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E7_Activity",),
)
P21_had_general_purpose = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P21_had_general_purpose",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E7_Activity",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E55_Type",),
)
P21i_was_purpose_of = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P21i_was_purpose_of",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E55_Type",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E7_Activity",),
)
P22_transferred_title_to = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P22_transferred_title_to",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E8_Acquisition",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E39_Actor",),
)
P22i_acquired_title_through = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P22i_acquired_title_through",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E39_Actor",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E8_Acquisition",),
)
P23_transferred_title_from = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P23_transferred_title_from",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E8_Acquisition",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E39_Actor",),
)
P23i_surrendered_title_through = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P23i_surrendered_title_through",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E39_Actor",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E8_Acquisition",),
)
P24_transferred_title_of = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P24_transferred_title_of",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E8_Acquisition",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E18_Physical_Thing",),
)
P24i_changed_ownership_through = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P24i_changed_ownership_through",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E18_Physical_Thing",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E8_Acquisition",),
)
P25_moved = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P25_moved",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E9_Move",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E19_Physical_Object",),
)
P25i_moved_by = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P25i_moved_by",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E19_Physical_Object",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E9_Move",),
)
P26_moved_to = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P26_moved_to",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E9_Move",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E53_Place",),
)
P26i_was_destination_of = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P26i_was_destination_of",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E53_Place",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E9_Move",),
)
P27_moved_from = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P27_moved_from",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E9_Move",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E53_Place",),
)
P27i_was_origin_of = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P27i_was_origin_of",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E53_Place",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E9_Move",),
)
P28_custody_surrendered_by = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P28_custody_surrendered_by",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E10_Transfer_of_Custody",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E39_Actor",),
)
P28i_surrendered_custody_through = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P28i_surrendered_custody_through",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E39_Actor",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E10_Transfer_of_Custody",),
)
P29_custody_received_by = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P29_custody_received_by",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E10_Transfer_of_Custody",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E39_Actor",),
)
P29i_received_custody_through = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P29i_received_custody_through",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E39_Actor",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E10_Transfer_of_Custody",),
)
P2_has_type = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P2_has_type",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E1_CRM_Entity",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E55_Type",),
)
P2i_is_type_of = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P2i_is_type_of",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E55_Type",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E1_CRM_Entity",),
)
P30_transferred_custody_of = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P30_transferred_custody_of",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E10_Transfer_of_Custody",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E18_Physical_Thing",),
)
P30i_custody_transferred_through = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P30i_custody_transferred_through",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E18_Physical_Thing",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E10_Transfer_of_Custody",),
)
P31_has_modified = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P31_has_modified",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E11_Modification",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E18_Physical_Thing",),
)
P31i_was_modified_by = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P31i_was_modified_by",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E18_Physical_Thing",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E11_Modification",),
)
P32_used_general_technique = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P32_used_general_technique",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E7_Activity",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E55_Type",),
)
P32i_was_technique_of = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P32i_was_technique_of",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E55_Type",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E7_Activity",),
)
P33_used_specific_technique = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P33_used_specific_technique",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E7_Activity",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E29_Design_or_Procedure",),
)
P33i_was_used_by = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P33i_was_used_by",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E29_Design_or_Procedure",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E7_Activity",),
)
P34_concerned = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P34_concerned",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E14_Condition_Assessment",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E18_Physical_Thing",),
)
P34i_was_assessed_by = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P34i_was_assessed_by",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E18_Physical_Thing",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E14_Condition_Assessment",),
)
P35_has_identified = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P35_has_identified",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E14_Condition_Assessment",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E3_Condition_State",),
)
P35i_was_identified_by = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P35i_was_identified_by",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E3_Condition_State",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E14_Condition_Assessment",),
)
P37_assigned = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P37_assigned",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E15_Identifier_Assignment",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E42_Identifier",),
)
P37i_was_assigned_by = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P37i_was_assigned_by",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E42_Identifier",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E15_Identifier_Assignment",),
)
P38_deassigned = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P38_deassigned",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E15_Identifier_Assignment",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E42_Identifier",),
)
P38i_was_deassigned_by = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P38i_was_deassigned_by",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E42_Identifier",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E15_Identifier_Assignment",),
)
P39_measured = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P39_measured",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E16_Measurement",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E18_Physical_Thing",),
)
P39i_was_measured_by = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P39i_was_measured_by",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E18_Physical_Thing",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E16_Measurement",),
)
P3_has_note = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P3_has_note",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E1_CRM_Entity",),
    range=("http://www.w3.org/2000/01/rdf-schema#Literal",),
)
P40_observed_dimension = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P40_observed_dimension",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E16_Measurement",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E54_Dimension",),
)
P40i_was_observed_in = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P40i_was_observed_in",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E54_Dimension",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E16_Measurement",),
)
P41_classified = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P41_classified",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E17_Type_Assignment",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E1_CRM_Entity",),
)
P41i_was_classified_by = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P41i_was_classified_by",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E1_CRM_Entity",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E17_Type_Assignment",),
)
P42_assigned = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P42_assigned",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E17_Type_Assignment",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E55_Type",),
)
P42i_was_assigned_by = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P42i_was_assigned_by",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E55_Type",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E17_Type_Assignment",),
)
P43_has_dimension = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P43_has_dimension",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E70_Thing",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E54_Dimension",),
)
P43i_is_dimension_of = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P43i_is_dimension_of",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E54_Dimension",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E70_Thing",),
)
P44_has_condition = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P44_has_condition",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E18_Physical_Thing",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E3_Condition_State",),
)
P44i_is_condition_of = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P44i_is_condition_of",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E3_Condition_State",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E18_Physical_Thing",),
)
P45_consists_of = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P45_consists_of",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E18_Physical_Thing",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E57_Material",),
)
P45i_is_incorporated_in = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P45i_is_incorporated_in",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E57_Material",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E18_Physical_Thing",),
)
P46_is_composed_of = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P46_is_composed_of",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E18_Physical_Thing",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E18_Physical_Thing",),
)
P46i_forms_part_of = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P46i_forms_part_of",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E18_Physical_Thing",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E18_Physical_Thing",),
)
P48_has_preferred_identifier = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P48_has_preferred_identifier",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E1_CRM_Entity",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E42_Identifier",),
)
P48i_is_preferred_identifier_of = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P48i_is_preferred_identifier_of",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E42_Identifier",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E1_CRM_Entity",),
)
P49_has_former_or_current_keeper = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P49_has_former_or_current_keeper",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E18_Physical_Thing",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E39_Actor",),
)
P49i_is_former_or_current_keeper_of = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P49i_is_former_or_current_keeper_of",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E39_Actor",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E18_Physical_Thing",),
)
P4_has_time_span = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P4_has_time-span",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E2_Temporal_Entity",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E52_Time-Span",),
)
P4i_is_time_span_of = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P4i_is_time-span_of",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E52_Time-Span",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E2_Temporal_Entity",),
)
P50_has_current_keeper = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P50_has_current_keeper",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E18_Physical_Thing",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E39_Actor",),
)
P50i_is_current_keeper_of = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P50i_is_current_keeper_of",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E39_Actor",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E18_Physical_Thing",),
)
P51_has_former_or_current_owner = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P51_has_former_or_current_owner",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E18_Physical_Thing",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E39_Actor",),
)
P51i_is_former_or_current_owner_of = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P51i_is_former_or_current_owner_of",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E39_Actor",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E18_Physical_Thing",),
)
P52_has_current_owner = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P52_has_current_owner",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E18_Physical_Thing",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E39_Actor",),
)
P52i_is_current_owner_of = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P52i_is_current_owner_of",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E39_Actor",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E18_Physical_Thing",),
)
P53_has_former_or_current_location = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P53_has_former_or_current_location",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E18_Physical_Thing",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E53_Place",),
)
P53i_is_former_or_current_location_of = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P53i_is_former_or_current_location_of",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E53_Place",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E18_Physical_Thing",),
)
P54_has_current_permanent_location = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P54_has_current_permanent_location",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E19_Physical_Object",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E53_Place",),
)
P54i_is_current_permanent_location_of = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P54i_is_current_permanent_location_of",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E53_Place",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E19_Physical_Object",),
)
P55_has_current_location = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P55_has_current_location",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E19_Physical_Object",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E53_Place",),
)
P55i_currently_holds = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P55i_currently_holds",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E53_Place",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E19_Physical_Object",),
)
P56_bears_feature = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P56_bears_feature",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E19_Physical_Object",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E26_Physical_Feature",),
)
P56i_is_found_on = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P56i_is_found_on",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E26_Physical_Feature",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E19_Physical_Object",),
)
P57_has_number_of_parts = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P57_has_number_of_parts",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E19_Physical_Object",),
    range=("http://www.w3.org/2000/01/rdf-schema#Literal",),
)
P59_has_section = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P59_has_section",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E18_Physical_Thing",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E53_Place",),
)
P59i_is_located_on_or_within = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P59i_is_located_on_or_within",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E53_Place",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E18_Physical_Thing",),
)
P5_consists_of = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P5_consists_of",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E3_Condition_State",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E3_Condition_State",),
)
P5i_forms_part_of = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P5i_forms_part_of",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E3_Condition_State",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E3_Condition_State",),
)
P62_depicts = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P62_depicts",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E24_Physical_Human-Made_Thing",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E1_CRM_Entity",),
)
P62i_is_depicted_by = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P62i_is_depicted_by",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E1_CRM_Entity",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E24_Physical_Human-Made_Thing",),
)
P65_shows_visual_item = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P65_shows_visual_item",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E24_Physical_Human-Made_Thing",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E36_Visual_Item",),
)
P65i_is_shown_by = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P65i_is_shown_by",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E36_Visual_Item",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E24_Physical_Human-Made_Thing",),
)
P67_refers_to = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P67_refers_to",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E89_Propositional_Object",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E1_CRM_Entity",),
)
P67i_is_referred_to_by = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P67i_is_referred_to_by",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E1_CRM_Entity",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E89_Propositional_Object",),
)
P68_foresees_use_of = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P68_foresees_use_of",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E29_Design_or_Procedure",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E57_Material",),
)
P68i_use_foreseen_by = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P68i_use_foreseen_by",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E57_Material",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E29_Design_or_Procedure",),
)
P69_has_association_with = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P69_has_association_with",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E29_Design_or_Procedure",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E29_Design_or_Procedure",),
)
P69i_is_associated_with = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P69i_is_associated_with",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E29_Design_or_Procedure",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E29_Design_or_Procedure",),
)
P70_documents = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P70_documents",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E31_Document",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E1_CRM_Entity",),
)
P70i_is_documented_in = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P70i_is_documented_in",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E1_CRM_Entity",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E31_Document",),
)
P71_lists = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P71_lists",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E32_Authority_Document",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E1_CRM_Entity",),
)
P71i_is_listed_in = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P71i_is_listed_in",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E1_CRM_Entity",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E32_Authority_Document",),
)
P72_has_language = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P72_has_language",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E33_Linguistic_Object",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E56_Language",),
)
P72i_is_language_of = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P72i_is_language_of",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E56_Language",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E33_Linguistic_Object",),
)
P73_has_translation = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P73_has_translation",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E33_Linguistic_Object",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E33_Linguistic_Object",),
)
P73i_is_translation_of = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P73i_is_translation_of",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E33_Linguistic_Object",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E33_Linguistic_Object",),
)
P74_has_current_or_former_residence = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P74_has_current_or_former_residence",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E39_Actor",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E53_Place",),
)
P74i_is_current_or_former_residence_of = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P74i_is_current_or_former_residence_of",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E53_Place",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E39_Actor",),
)
P75_possesses = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P75_possesses",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E39_Actor",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E30_Right",),
)
P75i_is_possessed_by = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P75i_is_possessed_by",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E30_Right",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E39_Actor",),
)
P76_has_contact_point = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P76_has_contact_point",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E39_Actor",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E41_Appellation",),
)
P76i_provides_access_to = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P76i_provides_access_to",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E41_Appellation",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E39_Actor",),
)
P79_beginning_is_qualified_by = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P79_beginning_is_qualified_by",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E52_Time-Span",),
    range=("http://www.w3.org/2000/01/rdf-schema#Literal",),
)
P7_took_place_at = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P7_took_place_at",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E4_Period",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E53_Place",),
)
P7i_witnessed = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P7i_witnessed",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E53_Place",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E4_Period",),
)
P80_end_is_qualified_by = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P80_end_is_qualified_by",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E52_Time-Span",),
    range=("http://www.w3.org/2000/01/rdf-schema#Literal",),
)
P81_ongoing_throughout = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P81_ongoing_throughout",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E52_Time-Span",),
    range=("http://www.w3.org/2000/01/rdf-schema#Literal",),
)
P81a_end_of_the_begin = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P81a_end_of_the_begin",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E52_Time-Span",),
    range=("http://www.w3.org/2000/01/rdf-schema#Literal",),
)
P81b_begin_of_the_end = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P81b_begin_of_the_end",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E52_Time-Span",),
    range=("http://www.w3.org/2000/01/rdf-schema#Literal",),
)
P82_at_some_time_within = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P82_at_some_time_within",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E52_Time-Span",),
    range=("http://www.w3.org/2000/01/rdf-schema#Literal",),
)
P82a_begin_of_the_begin = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P82a_begin_of_the_begin",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E52_Time-Span",),
    range=("http://www.w3.org/2000/01/rdf-schema#Literal",),
)
P82b_end_of_the_end = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P82b_end_of_the_end",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E52_Time-Span",),
    range=("http://www.w3.org/2000/01/rdf-schema#Literal",),
)
P86_falls_within = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P86_falls_within",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E52_Time-Span",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E52_Time-Span",),
)
P86i_contains = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P86i_contains",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E52_Time-Span",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E52_Time-Span",),
)
P89_falls_within = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P89_falls_within",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E53_Place",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E53_Place",),
)
P89i_contains = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P89i_contains",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E53_Place",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E53_Place",),
)
P8_took_place_on_or_within = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P8_took_place_on_or_within",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E4_Period",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E18_Physical_Thing",),
)
P8i_witnessed = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P8i_witnessed",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E18_Physical_Thing",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E4_Period",),
)
P90_has_value = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P90_has_value",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E54_Dimension",),
    range=("http://www.w3.org/2000/01/rdf-schema#Literal",),
)
P90a_has_lower_value_limit = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P90a_has_lower_value_limit",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E54_Dimension",),
    range=("http://www.w3.org/2000/01/rdf-schema#Literal",),
)
P90b_has_upper_value_limit = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P90b_has_upper_value_limit",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E54_Dimension",),
    range=("http://www.w3.org/2000/01/rdf-schema#Literal",),
)
P91_has_unit = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P91_has_unit",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E54_Dimension",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E58_Measurement_Unit",),
)
P91i_is_unit_of = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P91i_is_unit_of",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E58_Measurement_Unit",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E54_Dimension",),
)
P92_brought_into_existence = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P92_brought_into_existence",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E63_Beginning_of_Existence",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E77_Persistent_Item",),
)
P92i_was_brought_into_existence_by = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P92i_was_brought_into_existence_by",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E77_Persistent_Item",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E63_Beginning_of_Existence",),
)
P93_took_out_of_existence = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P93_took_out_of_existence",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E64_End_of_Existence",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E77_Persistent_Item",),
)
P93i_was_taken_out_of_existence_by = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P93i_was_taken_out_of_existence_by",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E77_Persistent_Item",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E64_End_of_Existence",),
)
P94_has_created = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P94_has_created",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E65_Creation",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E28_Conceptual_Object",),
)
P94i_was_created_by = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P94i_was_created_by",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E28_Conceptual_Object",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E65_Creation",),
)
P95_has_formed = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P95_has_formed",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E66_Formation",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E74_Group",),
)
P95i_was_formed_by = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P95i_was_formed_by",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E74_Group",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E66_Formation",),
)
P96_by_mother = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P96_by_mother",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E67_Birth",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E21_Person",),
)
P96i_gave_birth = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P96i_gave_birth",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E21_Person",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E67_Birth",),
)
P97_from_father = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P97_from_father",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E67_Birth",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E21_Person",),
)
P97i_was_father_for = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P97i_was_father_for",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E21_Person",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E67_Birth",),
)
P98_brought_into_life = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P98_brought_into_life",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E67_Birth",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E21_Person",),
)
P98i_was_born = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P98i_was_born",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E21_Person",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E67_Birth",),
)
P99_dissolved = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P99_dissolved",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E68_Dissolution",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E74_Group",),
)
P99i_was_dissolved_by = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P99i_was_dissolved_by",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E74_Group",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E68_Dissolution",),
)
P9_consists_of = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P9_consists_of",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E4_Period",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E4_Period",),
)
P9i_forms_part_of = OntologyProperty(
    "http://www.cidoc-crm.org/cidoc-crm/P9i_forms_part_of",
    domain=("http://www.cidoc-crm.org/cidoc-crm/E4_Period",),
    range=("http://www.cidoc-crm.org/cidoc-crm/E4_Period",),
)
