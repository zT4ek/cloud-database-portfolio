"""Build the Seoul portfolio CloudFormation template, using only the Python standard library."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
R = {}
def ref(name): return {"Ref": name}
def attr(name, key): return {"Fn::GetAtt": [name, key]}
def sub(value): return {"Fn::Sub": value}
def resource(name, kind, properties, depends=None):
    R[name] = {"Type": "AWS::" + kind, "Properties": properties}
    if depends: R[name]["DependsOn"] = depends
def read(name): return (HERE / name).read_text(encoding="utf-8")

resource("SiteBucket","S3::Bucket",{
    "PublicAccessBlockConfiguration":dict.fromkeys(["BlockPublicAcls","IgnorePublicAcls","BlockPublicPolicy","RestrictPublicBuckets"],True),
    "OwnershipControls":{"Rules":[{"ObjectOwnership":"BucketOwnerEnforced"}]},
    "BucketEncryption":{"ServerSideEncryptionConfiguration":[{"ServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}
})
resource("OriginAccess","CloudFront::OriginAccessControl",{"OriginAccessControlConfig":{
    "Name":sub("${AWS::StackName}-origin"),"OriginAccessControlOriginType":"s3","SigningBehavior":"always","SigningProtocol":"sigv4"}})
resource("Distribution","CloudFront::Distribution",{"DistributionConfig":{
    "Enabled":True,"Comment":"Youngtaek portfolio","HttpVersion":"http2and3","DefaultRootObject":"index.html","PriceClass":"PriceClass_200",
    "Origins":[{"Id":"PortfolioBucket","DomainName":attr("SiteBucket","RegionalDomainName"),
                "S3OriginConfig":{"OriginAccessIdentity":""},"OriginAccessControlId":ref("OriginAccess")}],
    "DefaultCacheBehavior":{"TargetOriginId":"PortfolioBucket","ViewerProtocolPolicy":"redirect-to-https","AllowedMethods":["GET","HEAD"],
        "Compress":True,"CachePolicyId":"658327ea-f89d-4fab-a63d-7e88639e58f6"}}})
resource("BucketPolicy","S3::BucketPolicy",{"Bucket":ref("SiteBucket"),"PolicyDocument":{"Version":"2012-10-17","Statement":[{
    "Effect":"Allow","Principal":{"Service":"cloudfront.amazonaws.com"},"Action":"s3:GetObject","Resource":sub("${SiteBucket.Arn}/*"),
    "Condition":{"StringEquals":{"AWS:SourceArn":sub("arn:${AWS::Partition}:cloudfront::${AWS::AccountId}:distribution/${Distribution}")}}}]}})
resource("Entries","DynamoDB::Table",{"BillingMode":"PAY_PER_REQUEST","AttributeDefinitions":[{"AttributeName":k,"AttributeType":"S"} for k in ["pk","sk"]],
    "KeySchema":[{"AttributeName":"pk","KeyType":"HASH"},{"AttributeName":"sk","KeyType":"RANGE"}]})
resource("Users","Cognito::UserPool",{"UserPoolName":sub("${AWS::StackName}-readers"),"UserPoolTier":"LITE",
    "UsernameAttributes":["email"],"AutoVerifiedAttributes":["email"],"UsernameConfiguration":{"CaseSensitive":False},
    "AccountRecoverySetting":{"RecoveryMechanisms":[{"Name":"verified_email","Priority":1}]},"MfaConfiguration":"OFF"})
stack_uuid={"Fn::Select":[2,{"Fn::Split":["/",ref("AWS::StackId")]}]}
domain={"Fn::Join":["",["yt-portfolio-",{"Fn::Select":[0,{"Fn::Split":["-",stack_uuid]}]}]]}
resource("LoginDomain","Cognito::UserPoolDomain",{"Domain":domain,"UserPoolId":ref("Users"),"ManagedLoginVersion":1})
callback=sub("https://${Distribution.DomainName}/guestbook.html")
resource("WebClient","Cognito::UserPoolClient",{"ClientName":"portfolio-browser","UserPoolId":ref("Users"),"GenerateSecret":False,
    "AllowedOAuthFlowsUserPoolClient":True,"AllowedOAuthFlows":["code"],"AllowedOAuthScopes":["openid","email"],
    "SupportedIdentityProviders":["COGNITO"],"CallbackURLs":[callback],"LogoutURLs":[callback],
    "ExplicitAuthFlows":["ALLOW_USER_SRP_AUTH","ALLOW_USER_PASSWORD_AUTH","ALLOW_REFRESH_TOKEN_AUTH"],
    "PreventUserExistenceErrors":"ENABLED"})
resource("Graph","AppSync::GraphQLApi",{"Name":sub("${AWS::StackName}-guestbook"),"AuthenticationType":"AMAZON_COGNITO_USER_POOLS",
    "UserPoolConfig":{"AwsRegion":ref("AWS::Region"),"UserPoolId":ref("Users"),"DefaultAction":"ALLOW"},
    "AdditionalAuthenticationProviders":[{"AuthenticationType":"API_KEY"}]})
resource("Schema","AppSync::GraphQLSchema",{"ApiId":attr("Graph","ApiId"),"Definition":read("schema.graphql")})
resource("ReaderKey","AppSync::ApiKey",{"ApiId":attr("Graph","ApiId"),"Expires":ref("KeyExpiry"),"Description":"Public guestbook query only"})
resource("DataRole","IAM::Role",{"AssumeRolePolicyDocument":{"Version":"2012-10-17","Statement":[{
    "Effect":"Allow","Principal":{"Service":"appsync.amazonaws.com"},"Action":"sts:AssumeRole","Condition":{
    "StringEquals":{"aws:SourceAccount":ref("AWS::AccountId")},"ArnLike":{"aws:SourceArn":attr("Graph","Arn")}}}]},
    "Policies":[{"PolicyName":"GuestbookItems","PolicyDocument":{"Version":"2012-10-17","Statement":[{
    "Effect":"Allow","Action":["dynamodb:Query","dynamodb:PutItem","dynamodb:DeleteItem","dynamodb:GetItem"],"Resource":attr("Entries","Arn")}]}}]})
resource("Data","AppSync::DataSource",{"ApiId":attr("Graph","ApiId"),"Name":"Guestbook","Type":"AMAZON_DYNAMODB",
    "ServiceRoleArn":attr("DataRole","Arn"),"DynamoDBConfig":{"AwsRegion":ref("AWS::Region"),"TableName":ref("Entries")}})
for name,typ,field,file in [("Read","Query","entries","list"),("Write","Mutation","write","write"),("Remove","Mutation","remove","remove")]:
    resource(name,"AppSync::Resolver",{"ApiId":attr("Graph","ApiId"),"TypeName":typ,"FieldName":field,"DataSourceName":attr("Data","Name"),
        "RequestMappingTemplate":read(file+"-request.vtl"),"ResponseMappingTemplate":read(file+"-response.vtl")},"Schema")
values={"Url":sub("https://${Distribution.DomainName}"),"Bucket":ref("SiteBucket"),"DistributionId":ref("Distribution"),"OacId":ref("OriginAccess"),
    "GraphUrl":attr("Graph","GraphQLUrl"),"GraphId":attr("Graph","ApiId"),"PoolId":ref("Users"),"ClientId":ref("WebClient"),
    "AuthUrl":{"Fn::Join":["",["https://",ref("LoginDomain"),".auth.",ref("AWS::Region"),".amazoncognito.com"]]},"Table":ref("Entries")}
template={"AWSTemplateFormatVersion":"2010-09-09","Description":"Youngtaek multipage student portfolio","Parameters":{"KeyExpiry":{"Type":"Number"}},
    "Resources":R,"Outputs":{k:{"Value":v} for k,v in values.items()}}
if __name__=="__main__": print(json.dumps(template,ensure_ascii=False))
