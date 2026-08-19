from dydantic import create_model_from_schema
import json

json_schema = {
    "title": "Person",
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "age": {"type": "integer"},
    },
    "required": ["name"],
}

Person = create_model_from_schema(json_schema)

person = Person(name="John", age=30)
print(person)  # Output: Person(name='John', age=30)
another = """
{
  "$id": "https://example.com/address.schema.json",
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "description": "An address similar to http://microformats.org/wiki/h-card",
  "type": "object",
  "properties": {
    "postOfficeBox": {
      "type": "string",
      "$comment": "Roles match the internal database user privileges."
    },
    "extendedAddress": {
      "type": "string"
    },
    "streetAddress": {
      "type": "string"
    },
    "locality": {
      "type": "string"
    },
    "region": {
      "type": "string"
    },
    "postalCode": {
      "type": "string"
    },
    "countryName": {
      "type": "string"
    }
  },
  "required": [ "locality", "region", "countryName" ],
  "dependentRequired": {
    "postOfficeBox": [ "streetAddress" ],
    "extendedAddress": [ "streetAddress" ]
  }
}
"""

address = create_model_from_schema(json.loads(another))

address = address(postOfficeBox="123 Main St", extendedAddress="Apt 4B", streetAddress="123 Main St", locality="Anytown", region="CA", postalCode="12345", countryName="USA")
print(address)  # Output: Address(postOfficeBox='123 Main St', extendedAddress='Apt 4B', streetAddress='123 Main St', locality='Anytown', region='CA', postalCode='12345', countryName='USA')


request_schema = """
{
  "$id": "https://example.com/address.schema.json",
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "description": "Request a record based on a user's name
  "type": "object",
  "properties": {
    "nameSearch
      "type": "string",
      "$comment": "Name of the user to search for"
    }
  }
}
"""

response_schema = """
{
  "$id": "https://example.com/address.schema.json",
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "description": "Response for a record based on a user's name
  "type": "object",
  "properties": {
    "nameSearch
      "type": "string",
      "$comment": "Name of the user to search for"
    }
  }
}
"""

test_stuff = """
{
  "$defs": {
    "request": {
      "searchQuery": {
        "type": "string",
        "maxLength": 100
      },
      "searchType": {
        "type": "string",
        "enum": ["firstName", "middleName", "lastName"]
      }
    }
  },
  "type": "object",
  "properties": {
    "request": {
        "$ref": "#/$defs/request"
    },
    "name": {
      "type": "object",
      "properties": {

        "firstName": {},
        "middleName": {},
        "lastName": {}
      }
    }
  },
  "required": [
    "lastName"
  ]
}
"""

test_stuff = create_model_from_schema(json.loads(test_stuff))
print("Fields in test_stuff model:")
for field in test_stuff.__fields__:
    print(field)


#est_stuff = test_stuff(name=test_stuff(query="John", firstName="John", middleName="John", lastName="John"))
#rint(test_stuff)  # Output: TestStuff(name=TestStuff(query='John', firstName='John', middleName='John', lastName='John'))