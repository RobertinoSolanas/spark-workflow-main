# SPARK Open-Source Roadmap

This document describes the phased open-source publication of SPARK.

## Release overview

|Release|Functional focus|Operational scope|
|-|-|-|
|First Release|Initial preprocessing and early procedural support|Covers document intake, extraction, and initial formal and plausibility checks|
|Second Release|Core substantive and legal review and assessment capabilities|AI-supported substantive checks and legal evaluation|
|Third Release|Participation, cross-cutting operational functions, and deployment assets|Completes the open-source publication|

### First Release — 2026-03-31

Release one provides the core preprocessing and early-stage procedural support capabilities of SPARK.

Included scope:

* Content extraction from application documents
* Formal completeness checks
* Plausibility checks
* Supporting backend services

### Second Release

Release two adds the capabilities for substantive completeness check, legal review and assessment and the drafting of decision. From this release onward, SPARK supports the complete handling of applications, with the exception of the participation of public authorities and the public.

The main frontend is published with this release.

Included scope:

* Substantive completeness checks
* Legal review and assessment
* Drafting of decisions
* Handling of legal changes
* Handling of plan changes
* Job status display
* Frontend

### Third Release

Release three completes the open-source publication. It adds participation of public authorities and the public, cross-cutting operational functions, and deployment assets.

Included scope:

* Participation of public authorities and the public
* Roles and rights management
* Approval workflows
* User management
* Logging
* Versioning of AI results
* Feedback mechanism
* Interactive training
* Helm charts for deployment

#### Deployment and operating model

With the third release, complete deployment scripts in the form of Helm charts are provided. The solution can be deployed and operated on a Kubernetes cluster, optionally using managed platform services.
The reference architecture relies on multiple open-source AI models. These models can either be deployed in a dedicated setup or accessed through an inference interface.

