# Alb module

validated, not deployed

Only approved client CIDRs may reach HTTP redirect and HTTPS. The certificate, access-log bucket and regional WAF ACL are externally supplied and not inspected by static validation. TLS terminates at the ALB; targets use the existing application HTTP ports. WAF content and backend TLS findings remain blocking until separately addressed.

Inputs and outputs are documented in variables.tf and outputs.tf.
