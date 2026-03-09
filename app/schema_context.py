RELATIONSHIP_MAP = {

    "virtualoffices": [
        "virtualoffices.property -> properties._id",
        "virtualoffices.partner -> users._id (role='partner')"
    ],

    "properties": [
        "properties.partner -> users._id (role='partner')"
    ],

    "seatbookings": [
        "seatbookings.user -> users._id",
        "seatbookings.paymentId -> payments._id",
        "seatbookings.seatIds -> coworkingspaces.floors.tables.seats._id"
    ],

    "reviews": [
        "reviews.user -> users._id",
        "reviews.space -> virtualoffices._id",
        "If spaceModel = 'MeetingRoom' -> meetingrooms._id",
        "If spaceModel = 'CoworkingSpace' -> coworkingspaces._id",
        "If spaceModel = 'VirtualOffice' -> virtualoffices._id"
    ],

    "meetingrooms": [
        "meetingrooms.property -> properties._id",
        "meetingrooms.partner -> users._id (role='partner')"
    ],

    "coworkingspaces": [
        "coworkingspaces.property -> properties._id",
        "coworkingspaces.partner -> users._id (role='partner')",
        "Embedded seats: coworkingspaces.floors.tables.seats._id"
    ],

    "payments": [
        "payments.user -> users._id",
        "payments.property -> properties._id",
        "payments.space -> virtualoffices._id" ,
        "virtualoffices.partner -> users._id (role='partner')"
    ],

    "invoices": [
        "invoices.user -> users._id",
        "invoices.partner -> users._id (role='partner')",
        "Business flow: invoice -> payment/booking -> space -> property"
    ],

    "bookings": [
        "bookings.user -> users._id",
        "bookings.partner -> users._id (role='partner')",
        "bookings.spaceId -> virtualoffices._id",
        "MeetingRoom -> meetingrooms._id",
        "CoworkingSpace -> coworkingspaces._id",
        "VirtualOffice -> virtualoffices._id"
    ],

    "users": [

    ]
}




SCHEMA = {
    
          

    # USERS (limited)
    "users": {
        "_id: ObjectId",
        "authProvider: str",
        "createdAt: datetime",
        "email: str",
        "fullName: str",
        "googleId: str",
        "isActive: bool",
        "isEmailVerified: bool",
        "isTwoFactorEnabled: bool",
        "kycVerified: bool",
        "lastLogin: datetime",
        "role: str",
        "updatedAt: datetime",

    },

    # BOOKINGS (restricted fields only from your structure)
    "bookings": {
                  "spaceId: str",
                  "spaceSnapshot._id: str",
                  "spaceSnapshot.address: str",
                  "spaceSnapshot.area: str",
                  "spaceSnapshot.city: str",
                  "spaceSnapshot.coordinates.lat: float",
                  "spaceSnapshot.coordinates.lng: float",
                  "spaceSnapshot.image: str",
                  "spaceSnapshot.name: str",
                  "startDate: datetime",
                  "status: str",
                  "timeline._id: ObjectId",
                  "timeline.by: str",
                  "timeline.date: datetime",
                  "timeline.note: str",
                  "timeline.status: str",
                  "timeline: list[object]",
                  "type: str",
                  "updatedAt: datetime",
                  "user: ObjectId"
     
    },



    # COWORKING SPACES
    "coworkingspaces": {
        
      "popular: bool",
      "_id: ObjectId",
      "finalPricePerMonth: int",
      "capacity: int",
      "operatingHours.openTime: str",
      "operatingHours.closeTime: str",
      "operatingHours.daysOpen.type: list",
      "operatingHours.daysOpen.items: str",
      "approvalStatus: str",
      "partnerPricePerMonth: int",
      "floors.type: list",
      "floors.items.floorNumber: int",
      "floors.items.name: str",
      "floors.items.tables.type: list",
      "floors.items.tables.items.tableNumber: str",
      "floors.items.tables.items.seats.type: list",
      "floors.items.tables.items.seats.items.seatNumber: str",
      "floors.items.tables.items.seats.items.isActive: bool",
      "floors.items.tables.items.seats.items._id: ObjectId",
      "floors.items.tables.items._id: ObjectId",
      "floors.items._id: ObjectId",
      "createdAt: datetime",
      "property: ObjectId",
      "sponsored: bool",
      "partner: ObjectId",
      "amenities.type: list",
      "amenities.items: str"

   
    },

    # INVOICES
    "invoices": {
        
                 "subtotal: int",
                "_id: ObjectId",
                "total: int",
                "taxRate: int",
                "user: ObjectId",
                "taxAmount: int",
                "description: str",
                "createdAt: datetime",
                "status: str",
                "partner: ObjectId",
                "invoiceNumber: str"
  
    },


    # PAYMENTS
    "payments": {
        
        "razorpayOrderId: str",
        "userEmail: str",
        "discountAmount: int",
        "currency: str",
        "totalAmount: int",
        "discountPercent: int",
        "_id: ObjectId",
        "space: ObjectId",
        "paymentType: str",
        "user: ObjectId",
        "spaceName: str",
        "yearlyPrice: int",
        "amount: int",
        "createdAt: datetime",
        "razorpayPaymentId: str",
        "tenure: int",
        "planKey: str",
        "planName: str",
        "userName: str",
        "status: str"


    },

      "virtualoffices":

  {
      "popular: bool",
      "approvalStatus: str  'values in status are ONLY ['completed','draft']' ",
      "isActive: bool",
      "updatedAt: datetime",
      "avgRating: int",
      "partner: ObjectId",
      "_id: ObjectId",
      "partnerMailingPricePerYear: int",
      "finalBrPricePerYear: int",
      "createdAt: datetime",
      "property: ObjectId",
      "sponsored: bool",
      "totalReviews: int",
      "finalMailingPricePerYear: int",
      "finalGstPricePerYear: int",
      "partnerGstPricePerYear: int",
      "partnerBrPricePerYear: int",
      "amenities.type: list",
      "amenities.items: str"


  }
,
    "meetingrooms" : {
        "popular: bool",
        "partnerPricePerDay: int",
        "minBookingHours: int",
        "partnerPricePerHour: int",
        "operatingHours.openTime: str",
        "operatingHours.closeTime: str",
        "operatingHours.daysOpen.type: list",
        "operatingHours.daysOpen.items: str",
        "approvalStatus: str 'values in status are ONLY ['active','draft']' ",
        "isActive: bool",
        "updatedAt: datetime",
        "avgRating: int",
        "finalPricePerDay: int",
        "type: str",
        "_id: ObjectId",
        "capacity: int",
        "finalPricePerHour: int",
        "createdAt: datetime",
        "property: ObjectId",
        "sponsored: bool",
        "totalReviews: int",
        "partner: ObjectId",
        "amenities.type: list",
        "amenities.items: str"

    },
    "reviews" : {
        "_id: ObjectId",
        "comment: str",
        "space: ObjectId",
        "user: ObjectId",
        "rating: int",
        "spaceModel: str",
        "createdAt: datetime"
    
    },

    "properties" :
    {
        
     "_id: ObjectId",
    "features.type: list",
    "features.items:list",
    "area: str",
    "name: str",
    "kycStatus: str",
    "createdAt: datetime",
    "location.type: str",
    "location.coordinates.type:list",
    "location.coordinates.items: float",
    "address: str",
    "isActive: bool",
    "images.type:list",
    "images.items: str",
    "status: str 'values in status are ONLY ['active','pending','draft']'",
    "updatedAt: datetime",
    "partner: ObjectId",
    "city: str"
    },

    "seatbookings":{
        "startTime: datetime",
        "paymentId: str",
        "_id: ObjectId",
        "user: ObjectId",
        "createdAt: datetime",
        "seatIds.type: unknown",
        "seatIds.items: ObjectId",
        "space: ObjectId",
        "updatedAt: datetime",
        "endTime: datetime",
        "totalAmount: int",
        "status: str"
     
    }


}





def build_context(collections):
    context = ""

    for col in collections:
        if col in SCHEMA:
            context += f"\nCollection: {col}\n"
            context += "Fields:\n"
            for field in SCHEMA[col]:
                context += f"- {field}\n"

            if col in RELATIONSHIP_MAP:
                context += "Relationships:\n"
                for rel in RELATIONSHIP_MAP[col]:
                    context += f"- {rel}\n"

    return context