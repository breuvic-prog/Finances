"""Imports"""
import re

"""Constants"""
TRUE = "true"
FALSE = "false"

class StringManager:
    
    @staticmethod
    def Capitalize(string):
        #Splits the string by the spaces
        parts = string.split()
        words_not_to_capitalize = ["is", "of"]
        
        #Capitalizes all individual parts
        for i in range(len(parts)):
            
            #Lowercases everything for consistency
            parts[i] = parts[i].lower()
            
            #Capitalizes words that need capitalize            
            if i == 0 or not (parts[i] in words_not_to_capitalize):
                parts[i] = parts[i].capitalize()
            
                
        
        return " ".join(parts)
        
    @staticmethod
    def Lowercase(string):
        #Splits the string by the spaces
        parts = string.split()
        
        #Lowercases all individual parts
        for i in range(len(parts)):
            
            #Lowercases everything for consistency
            parts[i] = parts[i].lower()                            
        
        return " ".join(parts)     
        
    @staticmethod
    def Condense(string):
        return string.replace(" ", "")

    @staticmethod
    def Create_Namespace(addon_name):

        name_parts = addon_name.split()
        namespace = ""

        if len(name_parts) > 1:
            for word in name_parts:
                namespace += StringManager.Lowercase(word[0])
        else:
            namespace = StringManager.Lowercase(addon_name)

        return namespace

    @staticmethod
    def Apply_Snake_Case(string):
        string = StringManager.Lowercase(string)

        # Remove anything that is not a letter, number, or space
        string = re.sub(r"[^a-z0-9\s]", "", string)

        # Replace one or more spaces with a single underscore
        string = re.sub(r"\s+", "_", string)

        return string

    """Conversion Check Methods"""
    @staticmethod
    def can_convert_to_bool(string) -> bool:
        # Converts the whole string to lowercase
        lowercase_string = StringManager.Lowercase(string)

        return lowercase_string == TRUE or lowercase_string == FALSE
    @staticmethod
    def can_convert_to_int(string) -> bool:
        try:
            int(string)
            return True
        except (ValueError, TypeError):
            return False
    @staticmethod
    def can_convert_to_float(string) -> bool:
        try:
            float(string)
            return True
        except ValueError:
            return False


